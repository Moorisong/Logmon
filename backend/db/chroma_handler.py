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

# Chroma DB 클라이언트 지연 초기화
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
        
    # Null 또는 빈 텍스트 방어, 너무 짧은 경우 바로 반환
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = min(start + chunk_size, text_length)
        
        # 문서의 마지막이 아니라면 문장 끝(줄바꿈, 마침표)에서 끊기 위해 뒤로 이동 탐색
        if end < text_length:
            # 안전하게 자르기 위해 줄바꿈(\n) 위치 탐색
            last_newline = text.rfind('\n', start, end)
            if last_newline != -1 and (end - last_newline) < 200:
                end = last_newline + 1
            else:
                # 마침표, 물음표 등 탐색
                match = re.search(r'[.!?]\s', text[start:end][::-1])
                if match:
                    end = end - match.start()
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
            
        start = end - overlap
        
        # 무한 루프 방지
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
        # 타임아웃 15초 부여하여 서버 무응답 방어
        response = requests.post(url, json=payload, timeout=15.0)
        response.raise_for_status()
        data = response.json()
        return data.get("embedding", [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama 임베딩 생성 실패: {e}")
        # 예외를 상위로 전파하여 트랜잭션 등에서 처리할 수 있도록 함
        raise

def process_and_store_vector(log_id: int, data: Dict[str, Any]):
    """
    raw_message를 청킹하고, 임베딩을 추출하여 Chroma DB에 적재합니다.
    메타데이터에 id와 user_key를 반드시 포함시킵니다 (멀티테넌시 격리 방어).
    """
    raw_message = data.get("raw_message")
    if not raw_message:
        return # 저장할 비정형 텍스트 없음
        
    user_key = data.get("user_key")
    timestamp = data.get("timestamp")
    source_tool = data.get("source_tool", "UNKNOWN_TOOL")
    
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
            
            # 메타데이터 격리 제어 (보안 락)
            metadatas.append({
                "id": log_id,
                "user_key": user_key,
                "timestamp": timestamp,
                "source_tool": source_tool,
                "chunk_index": i
            })
            
            # 고유 ID 체계: {레코드ID}_{청크인덱스}
            ids.append(f"{log_id}_{i}")
            
        except Exception as e:
            logger.error(f"청크 {i} 임베딩/적재 중 에러 발생: {e}")
            # 일부 실패하더라도 전체가 중단되지 않도록 로그만 남기고 계속 진행할지 여부 결정 (현재는 계속 진행)
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

def query_vectors(query_text: str, n_results: int = 3, user_key: str = "") -> List[List[str]]:
    """
    사용자의 질문 텍스트를 임베딩하여 Chroma DB에서 유사도가 높은 문서(청크)를 조회합니다.
    user_key 메타데이터 필터를 통해 타인의 데이터 조회를 원천 차단합니다.
    """
    if not query_text:
        return []
        
    try:
        # 질문 문자열 벡터화
        query_embedding = get_embedding(query_text)
        if not query_embedding:
            return []
            
        collection = get_collection()
        
        # user_key 메타데이터 필터 구성
        where_filter = {}
        if user_key:
            where_filter = {"user_key": user_key}
            
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents"] # 메타데이터나 거리가 아닌 텍스트 문서만 반환
        )
        
        # results["documents"] 포맷: [[doc1, doc2, ...]]
        return results.get("documents", [])
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
