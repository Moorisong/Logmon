import os
import re
import logging
import requests
import chromadb
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def get_chroma_dir():
    return os.getenv("LOGMON_CHROMA_DIR", "/app/data/chroma")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBEDDING_MODEL = "nomic-embed-text"
COLLECTION_NAME = "ide_logs"

_chroma_client = None

def get_chroma_client() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        chroma_dir = get_chroma_dir()
        if not os.path.exists(chroma_dir):
            os.makedirs(chroma_dir, exist_ok=True)
            logger.info(f"Chroma DB 디렉토리 생성: {chroma_dir}")
        _chroma_client = chromadb.PersistentClient(path=chroma_dir)
    return _chroma_client

def get_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """
    N95 CPU 저전력 최적화를 위해 Langchain 없이 구현된 자체 초경량 텍스트 청킹 함수.
    줄바꿈과 정규식을 활용하여 문장/단락의 의미를 최대한 훼손하지 않으면서 쪼갭니다.
    """
    if not text:
        return []
        
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = min(start + chunk_size, text_length)
        
        if end < text_length:
            last_newline = text.rfind('\n', start, end)
            if last_newline != -1 and (end - last_newline) < 200:
                end = last_newline + 1
            else:
                match = re.search(r'[.!?]\s', text[start:end][::-1])
                if match:
                    end = end - match.start()
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
            
        start = end - overlap
        
        if start <= 0 or end == text_length:
            start = end

    return chunks

def get_embedding(text: str) -> List[float]:
    """
    Ollama API를 호출하여 텍스트의 임베딩 벡터를 반환합니다.
    """
    url = f"{OLLAMA_HOST}/api/embeddings"
    payload = {
        "model": EMBEDDING_MODEL,
        "prompt": text
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15.0)
        response.raise_for_status()
        data = response.json()
        return data.get("embedding", [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama 임베딩 생성 실패: {e}")
        raise

def process_and_store_vector(log_id: int, data: Dict[str, Any]):
    """
    raw_message를 청킹하고, 임베딩을 추출하여 Chroma DB에 적재합니다.
    메타데이터에 id와 user_key를 반드시 포함시킵니다 (멀티테넌시 격리 방어).
    """
    raw_message = data.get("raw_message")
    if not raw_message:
        return
        
    user_key = data.get("user_key")
    timestamp = data.get("timestamp")
    source_tool = data.get("source_tool", "UNKNOWN_TOOL")
    event_type = data.get("event_type", "INFO")
    
    chunks = chunk_text(raw_message, chunk_size=800, overlap=100)
    
    collection = get_collection()
    
    docs = []
    embeddings = []
    metadatas = []
    ids = []
    
    for i, chunk in enumerate(chunks):
        try:
            vector = get_embedding(chunk)
            if not vector:
                continue
                
            docs.append(chunk)
            embeddings.append(vector)
            
            # Determine chunk-specific event type if the incoming event_type is generic (like LOG_DUMP)
            chunk_event_type = event_type
            if event_type == "LOG_DUMP":
                chunk_lower = chunk.lower()
                if any(w in chunk_lower for w in ["[error]", "error:", "exception:", "fail", "오류"]):
                    chunk_event_type = "ERROR"
                elif any(w in chunk_lower for w in ["[warning]", "warning:", "warn:", "경고"]):
                    chunk_event_type = "WARNING"
                else:
                    chunk_event_type = "INFO"

            metadatas.append({
                "id": log_id,
                "user_key": user_key,
                "timestamp": timestamp,
                "source_tool": source_tool,
                "event_type": chunk_event_type,
                "chunk_index": i
            })
            
            ids.append(f"{log_id}_{i}")
            
        except Exception as e:
            logger.error(f"청크 {i} 임베딩/적재 중 에러 발생: {e}")
            continue
            
    if docs:
        try:
            collection.add(
                documents=docs,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Chroma DB 벡터 적재 완료: log_id {log_id}, 청크 {len(docs)}개")
        except Exception as e:
            logger.error(f"Chroma DB 컬렉션 add 실패: {e}")
            raise

def query_vectors(
    query_text: str,
    n_results: int = 3,
    user_key: str = "",
    event_type: str = "",
    start_time: str = None,
    end_time: str = None,
    keywords: List[str] = None
) -> List[List[str]]:
    """
    사용자의 질문 텍스트를 임베딩하여 Chroma DB에서 유사도가 높은 문서(청크)를 조회합니다.
    시간 범위(start_time, end_time) 및 특정 키워드(keywords) 필터 조건을 안전하게 후처리 적용합니다.
    """
    if not query_text:
        return []
        
    try:
        query_embedding = get_embedding(query_text)
        if not query_embedding:
            return []
            
        collection = get_collection()
        
        filters = []
        if user_key:
            filters.append({"user_key": user_key})
        if event_type:
            filters.append({"event_type": event_type})
            
        where_filter = {}
        if len(filters) == 1:
            where_filter = filters[0]
        elif len(filters) > 1:
            where_filter = {"$and": filters}
            
        # 시간, 키워드 등의 필터링이 필요한 경우 충분한 모수를 가져와 후처리
        q_lower = query_text.lower()
        has_extra_filters = bool(
            start_time or end_time or keywords or 
            any(w in q_lower for w in ["오늘", "today", "투데이", "어제", "새벽", "일주일", "분"])
        )
        query_n = 100 if has_extra_filters else n_results
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=query_n,
            where=where_filter if where_filter else None,
            include=["documents", "metadatas"]
        )
        
        docs = results.get("documents", [])[0] if results.get("documents") else []
        metas = results.get("metadatas", [])[0] if results.get("metadatas") else []
        
        filtered_docs = []
        for doc, meta in zip(docs, metas):
            ts = meta.get("timestamp", "")
            
            # 1. 시간 범위 필터 적용
            if start_time and ts < start_time:
                continue
            if end_time and ts > end_time:
                continue
                
            # 2. 오늘 날짜 예외 보완 필터 (오늘/투데이/today 있고 구체적 시각 범위가 없을 때)
            if not start_time and not end_time:
                if any(w in q_lower for w in ["오늘", "today", "투데이"]):
                    import datetime
                    timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
                    kst_now = datetime.datetime.now(timezone_kst)
                    today_date_str = kst_now.strftime("%Y-%m-%d")
                    if not ts or not ts.startswith(today_date_str):
                        continue
            
            # 3. 키워드 필터 적용
            if keywords:
                doc_lower = doc.lower()
                if not any(kw.lower() in doc_lower for kw in keywords):
                    continue
                    
            filtered_docs.append(doc)
            if len(filtered_docs) >= n_results:
                break
                
        return [filtered_docs]
    except Exception as e:
        logger.error(f"query_vectors 조회 중 에러 발생: {e}")
        return []

def delete_vectors_by_log_ids(log_ids: List[int]):
    """
    주어진 SQLite 로그 ID 리스트와 매핑되는 Chroma DB 벡터 청크들을 일괄 삭제합니다.
    """
    if not log_ids:
        return
        
    try:
        collection = get_collection()
        collection.delete(
            where={"id": {"$in": log_ids}}
        )
        logger.info(f"Chroma DB 벡터 클리닝 완료. 연동된 로그 ID 수: {len(log_ids)}")
    except Exception as e:
        logger.error(f"Chroma DB 벡터 클리닝 중 에러 발생: {e}")

def delete_vectors_by_user_key(user_key: str):
    """
    특정 user_key 메타데이터 조건 필터를 만족하는 모든 Chroma DB 임베딩 벡터를 일괄 삭제 파쇄합니다.
    """
    if not user_key:
        return
        
    try:
        collection = get_collection()
        collection.delete(
            where={"user_key": user_key}
        )
        logger.info(f"⚙️ Chroma DB 벡터 클리닝 완료. 삭제 처리된 user_key 격리 영역: {user_key}")
    except Exception as e:
        logger.error(f"Chroma DB 멀티테넌시 벡터 영역 파쇄 중 예외 에러 발생: {e}")