"""
ChromaDB 클라이언트 관리, 임베딩 생성, 벡터 적재 모듈.
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
    if not text: return []
    if len(text) <= chunk_size: return [text]
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length:
            last_newline = text.rfind('\n', start, end)
            if last_newline != -1 and (end - last_newline) < 200: end = last_newline + 1
            else:
                match = re.search(r'[.!?]\s', text[start:end][::-1])
                if match: end = end - match.start()
        chunk = text[start:end].strip()
        if chunk: chunks.append(chunk)
        start = end - overlap
        if start <= 0 or end == text_length: start = end
    return chunks

def get_embedding(text: str) -> List[float]:
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
    raw_message = data.get("raw_message")
    if not raw_message: return

    user_key = data.get("user_key")
    timestamp = data.get("timestamp", "")
    source_tool = data.get("source_tool", "UNKNOWN_TOOL")
    event_type = data.get("event_type", "INFO")
    
    # [핵심 수정] task_name을 가져와서 action_type으로 직접 매핑
    task_name = data.get("task_name", "UNKNOWN")
    action_type = task_name if task_name != "UNKNOWN" else classify_action_type(raw_message)

    timestamp_epoch = timestamp_to_epoch(timestamp)
    source_ide = classify_source_ide_from_fields(source_tool, raw_message)

    chunks = chunk_text(raw_message, chunk_size=800, overlap=100)
    collection = get_collection()

    docs, embeddings, metadatas, ids = [], [], [], []

    for i, chunk in enumerate(chunks):
        try:
            vector = get_embedding(chunk)
            if not vector: continue

            docs.append(chunk)
            embeddings.append(vector)

            metadatas.append({
                "id": str(log_id),
                "user_key": user_key,
                "timestamp": timestamp,
                "timestamp_epoch": timestamp_epoch,
                "source_ide": source_ide,
                "event_type": event_type,
                "action_type": action_type,  # LLM이 식별 가능한 Action 이름
                "chunk_index": i,
            })
            ids.append(f"{log_id}_{i}")
        except Exception as e:
            logger.error(f"청크 {i} 임베딩 실패: {e}")
            continue

    if docs:
        collection.upsert(documents=docs, embeddings=embeddings, metadatas=metadatas, ids=ids)
        logger.info(f"Chroma DB 적재 완료 [ID: {log_id}, Action: {action_type}]")