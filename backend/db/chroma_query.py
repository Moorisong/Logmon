import datetime
import logging
from typing import List, Optional, Any

logger = logging.getLogger(__name__)

def _build_where_filter(
    user_key: str,
    event_type: str,
    log_level: str,
    source_ide: str,
    action_type: str,
) -> dict:
    """ChromaDB where 필터를 간소화하여 데이터 확보율을 높입니다."""
    conditions = []
    if user_key: conditions.append({"user_key": {"$eq": user_key}})
    # 메타데이터 필터링을 지나치게 좁히지 않기 위해 필수 항목만 적용
    if event_type: conditions.append({"event_type": {"$eq": event_type}})
    
    if not conditions: return {}
    return {"$and": conditions} if len(conditions) > 1 else conditions[0]

def query_vectors(
    query_text: str,
    n_results: int = 5,
    user_key: str = "",
    event_type: str = "",
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    keywords: List[str] = None,
    log_level: str = "",
    source_ide: str = "",
    action_type: str = "",
) -> List[List[Any]]:
    """
    엄격한 필터링을 제거하고, 유사도 검색 결과에 집중하여 데이터를 LLM에 전달합니다.
    rag_engine.py의 unpack 규격에 맞추어 [docs, distances, metadatas]를 반환합니다.
    """
    from backend.db.chroma_handler import get_collection, get_embedding

    if not query_text: return [[], [], []]

    try:
        query_embedding = get_embedding(query_text)
        collection = get_collection()
        
        # 1. 벡터 기반 유사도 검색 (최대한 많이 가져옴)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=20, 
            where=_build_where_filter(user_key, event_type, log_level, source_ide, action_type) if user_key else None,
            include=["documents", "distances", "metadatas"]
        )

        raw_docs = results.get("documents", [[]])[0]
        raw_distances = results.get("distances", [[]])[0] if results.get("distances") else []
        raw_metas = results.get("metadatas", [[]])[0]

        # 2. 문서에 DATE 정보 삽입 (rag_engine에서 IDE 정보와 결합됨)
        docs = [f"[DATE: {m.get('timestamp', 'Unknown')}]\n{d}" for d, m in zip(raw_docs, raw_metas)]
        
        # [핵심 수정] rag_engine이 zip(raw_docs, raw_metas)를 정상 수행하도록 3단 구조 유지
        return [docs, raw_distances, raw_metas]

    except Exception as e:
        logger.error(f"query_vectors 검색 실패함: {e}")
        return [[], [], []]

def delete_vectors_by_log_ids(log_ids: List[int]) -> None:
    from backend.db.chroma_handler import get_collection
    collection = get_collection()
    collection.delete(where={"id": {"$in": log_ids}})

def delete_vectors_by_user_key(user_key: str) -> None:
    from backend.db.chroma_handler import get_collection
    collection = get_collection()
    collection.delete(where={"user_key": user_key})