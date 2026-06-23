# backend/db/chroma_handler.py
"""
ChromaDB 클라이언트 관리, 임베딩 생성, 벡터 적재 모듈.
벡터 조회/삭제는 chroma_query.py에 위임합니다.
메타데이터 유틸은 chroma_meta_utils.py에 위임합니다.
"""
import os
import re
import logging
import requests
import chromadb
from typing import List, Dict, Any

from backend.llm.ide_classifier import classify_source_ide_from_fields
from backend.db.chroma_meta_utils import (
    classify_action_type,
    timestamp_to_epoch,
    normalize_log_level,
)
# 하위 호환성: 외부 코드가 chroma_handler에서 직접 임포트하던 심볼 유지
from backend.db.chroma_query import (
    query_vectors,
    delete_vectors_by_log_ids,
    delete_vectors_by_user_key,
)

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBEDDING_MODEL = "nomic-embed-text"
COLLECTION_NAME = "ide_logs"

_chroma_client = None


def get_chroma_dir() -> str:
    return os.getenv("LOGMON_CHROMA_DIR", "/app/data/chroma")


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
    """Ollama API를 호출하여 텍스트의 임베딩 벡터를 반환합니다."""
    url = f"{OLLAMA_HOST}/api/embeddings"
    payload = {"model": EMBEDDING_MODEL, "prompt": text}
    try:
        response = requests.post(url, json=payload, timeout=60.0)
        response.raise_for_status()
        return response.json().get("embedding", [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama 임베딩 생성 실패: {e}")
        raise


def process_and_store_vector(log_id: int, data: Dict[str, Any]):
    """
    raw_message를 청킹하고, 임베딩을 추출하여 Chroma DB에 적재합니다.
    메타데이터 스키마:
      - id, user_key, chunk_index (기존)
      - timestamp (str), timestamp_epoch (int, Epoch 초)
      - event_type (기존), log_level (INFO/ERROR/WARN/DEBUG)
      - source_tool (기존), source_ide (IDE 분류 문자열)
      - action_type (network/build/git/system)
    """
    raw_message = data.get("raw_message")
    if not raw_message:
        return

    user_key = data.get("user_key")
    timestamp = data.get("timestamp", "")
    source_tool = data.get("source_tool", "UNKNOWN_TOOL")
    event_type = data.get("event_type", "INFO")

    timestamp_epoch = timestamp_to_epoch(timestamp)
    source_ide = classify_source_ide_from_fields(source_tool, raw_message)
    action_type = classify_action_type(raw_message)

    chunks = chunk_text(raw_message, chunk_size=800, overlap=100)
    collection = get_collection()

    docs: List[str] = []
    embeddings: List[List[float]] = []
    metadatas: List[Dict[str, Any]] = []
    ids: List[str] = []

    for i, chunk in enumerate(chunks):
        try:
            vector = get_embedding(chunk)
            if not vector:
                continue

            docs.append(chunk)
            embeddings.append(vector)

            chunk_event_type = event_type
            if event_type == "LOG_DUMP":
                chunk_lower = chunk.lower()
                if any(w in chunk_lower for w in ["[error]", "error:", "exception:", "fail", "오류"]):
                    chunk_event_type = "ERROR"
                elif any(w in chunk_lower for w in ["[warning]", "warning:", "warn:", "경고"]):
                    chunk_event_type = "WARNING"
                else:
                    chunk_event_type = "INFO"

            chunk_log_level = normalize_log_level(chunk_event_type, chunk)

            metadatas.append({
                "id": log_id,
                "user_key": user_key,
                "timestamp": timestamp,
                "timestamp_epoch": timestamp_epoch,
                "source_tool": source_tool,
                "source_ide": source_ide,
                "event_type": chunk_event_type,
                "log_level": chunk_log_level,
                "action_type": action_type,
                "chunk_index": i,
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
                ids=ids,
            )
            logger.info(f"Chroma DB 벡터 적재 완료: log_id {log_id}, 청크 {len(docs)}개")
        except Exception as e:
            logger.error(f"Chroma DB 컬렉션 add 실패: {e}")
            raise