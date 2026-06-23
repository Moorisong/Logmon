# backend/db/chroma_query.py
"""
ChromaDB 벡터 조회 및 삭제 함수.
LLM 추출 메타데이터 필터(log_level, source_ide, action_type)를 포함한 확장 쿼리를 지원합니다.
"""
import datetime
import logging
from typing import List

logger = logging.getLogger(__name__)

_TZ_KST = datetime.timezone(datetime.timedelta(hours=9))


def _build_where_filter(
    user_key: str,
    event_type: str,
    log_level: str,
    source_ide: str,
    action_type: str,
) -> dict:
    """ChromaDB where 필터 딕셔너리를 구성합니다."""
    conditions = []
    if user_key:
        conditions.append({"user_key": {"$eq": user_key}})
    if event_type:
        conditions.append({"event_type": {"$eq": event_type}})
    if log_level:
        conditions.append({"log_level": {"$eq": log_level}})
    if source_ide:
        conditions.append({"source_ide": {"$eq": source_ide}})
    if action_type:
        conditions.append({"action_type": {"$eq": action_type}})

    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _apply_python_filters(
    docs: list, metas: list,
    user_key: str, event_type: str,
    log_level: str, source_ide: str, action_type: str,
    start_time: str, end_time: str,
    keywords: List[str], q_lower: str,
    n_results: int,
) -> list:
    """ChromaDB 쿼리 결과를 파이썬 단에서 추가 필터링합니다."""
    filtered = []
    for doc, meta in zip(docs, metas):
        if user_key and meta.get("user_key") != user_key:
            continue
        if event_type and meta.get("event_type") != event_type:
            continue
        if log_level and meta.get("log_level") != log_level:
            continue
        if source_ide and meta.get("source_ide") != source_ide:
            continue
        if action_type and meta.get("action_type") != action_type:
            continue

        ts = meta.get("timestamp", "")
        if start_time and ts < start_time:
            continue
        if end_time and ts > end_time:
            continue

        # 오늘 날짜 보완 필터
        if not start_time and not end_time:
            if any(w in q_lower for w in ["오늘", "today", "투데이"]):
                today_str = datetime.datetime.now(_TZ_KST).strftime("%Y-%m-%d")
                if not ts or not ts.startswith(today_str):
                    continue

        if keywords:
            doc_lower = doc.lower()
            if not any(kw.lower() in doc_lower for kw in keywords):
                continue

        filtered.append(doc)
        if len(filtered) >= n_results:
            break

    return filtered


def query_vectors(
    query_text: str,
    n_results: int = 3,
    user_key: str = "",
    event_type: str = "",
    start_time: str = None,
    end_time: str = None,
    keywords: List[str] = None,
    log_level: str = "",
    source_ide: str = "",
    action_type: str = "",
) -> List[List[str]]:
    """
    사용자의 질문 텍스트를 임베딩하여 Chroma DB에서 유사도가 높은 문서(청크)를 조회합니다.
    시간 범위(start_time, end_time), 키워드(keywords) 외에
    LLM 추출 메타데이터 필터(log_level, source_ide, action_type)도 적용합니다.
    """
    # 순환 임포트 방지를 위해 로컬 임포트
    from backend.db.chroma_handler import get_collection, get_embedding

    if not query_text:
        return []

    try:
        query_embedding = get_embedding(query_text)
        if not query_embedding:
            return []

        collection = get_collection()
        where_filter = _build_where_filter(
            user_key, event_type, log_level, source_ide, action_type
        )

        q_lower = query_text.lower()
        has_extra_filters = bool(
            start_time or end_time or keywords
            or any(w in q_lower for w in ["오늘", "today", "투데이", "어제", "새벽", "일주일", "분"])
        )
        query_n = 100 if has_extra_filters else n_results

        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=query_n,
                where=where_filter if where_filter else None,
                include=["documents", "metadatas"],
            )
        except Exception as query_err:
            logger.warning(
                f"Chroma DB 쿼리 실패(필터 문제 의심). 전체 검색으로 Fallback합니다. 에러: {query_err}"
            )
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=150,
                include=["documents", "metadatas"],
            )

        raw_docs = results.get("documents", [])[0] if results.get("documents") else []
        raw_metas = results.get("metadatas", [])[0] if results.get("metadatas") else []

        filtered = _apply_python_filters(
            raw_docs, raw_metas,
            user_key, event_type, log_level, source_ide, action_type,
            start_time, end_time, keywords or [], q_lower, n_results,
        )
        return [filtered]

    except Exception as e:
        logger.error(f"query_vectors 조회 중 에러 발생: {e}")
        return []


def delete_vectors_by_log_ids(log_ids: List[int]) -> None:
    """주어진 SQLite 로그 ID 리스트와 매핑되는 Chroma DB 벡터 청크들을 일괄 삭제합니다."""
    if not log_ids:
        return
    from backend.db.chroma_handler import get_collection
    try:
        collection = get_collection()
        collection.delete(where={"id": {"$in": log_ids}})
        logger.info(f"Chroma DB 벡터 클리닝 완료. 연동된 로그 ID 수: {len(log_ids)}")
    except Exception as e:
        logger.error(f"Chroma DB 벡터 클리닝 중 에러 발생: {e}")


def delete_vectors_by_user_key(user_key: str) -> None:
    """특정 user_key에 해당하는 모든 Chroma DB 임베딩 벡터를 일괄 삭제합니다."""
    if not user_key:
        return
    from backend.db.chroma_handler import get_collection
    try:
        collection = get_collection()
        collection.delete(where={"user_key": user_key})
        logger.info(f"⚙️ Chroma DB 벡터 클리닝 완료. user_key: {user_key}")
    except Exception as e:
        logger.error(f"Chroma DB 멀티테넌시 벡터 파쇄 중 예외 에러 발생: {e}")
