import logging
import datetime
import sqlite3
import os
from typing import Optional

from backend.db.chroma_handler import query_vectors
from backend.llm.client import generate_completion
from backend.llm.prompt_templates import RAG_PROMPT_TEMPLATE
from backend.llm.guardrail import check_guardrail, GUARDRAIL_FALLBACK_MSG
from backend.llm.reranker import rerank_documents
from backend.llm.utils import postprocess_noun_ending, parse_relative_datetime

logger = logging.getLogger(__name__)
_TZ_KST = datetime.timezone(datetime.timedelta(hours=9))
CURRENT_SYS_TIME = "2026-06-24"

def get_exact_log_counts(start_time: Optional[str], end_time: Optional[str]) -> tuple:
    """SQLite DB에서 특정 기간 동안의 실제 ERROR 및 WARN 로그 개수를 정확히 카운트합니다."""
    db_dir = os.environ.get("LOGMON_DB_DIR", "/app/data")
    db_path = os.path.join(db_dir, "logmon.db")
    
    error_count, warn_count = 0, 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        base_time = start_time if start_time else (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat()
        
        q_err = "SELECT COUNT(*) FROM ide_activity_logs WHERE event_type LIKE '%ERROR%' AND timestamp >= ?"
        q_warn = "SELECT COUNT(*) FROM ide_activity_logs WHERE event_type LIKE '%WARN%' AND timestamp >= ?"
        
        cursor.execute(q_err, (base_time,))
        error_count = cursor.fetchone()[0]
        cursor.execute(q_warn, (base_time,))
        warn_count = cursor.fetchone()[0]
        conn.close()
    except Exception as e:
        logger.error(f"❌ 실시간 통계 조회 오류: {e}")
    return error_count, warn_count

async def ask_rag_agent(question: str, user_key: str, top_k: int = 5) -> str:
    logger.info(f"RAG 질의 시작 (Stateless Mode): {question}")
    
    if not check_guardrail(question):
        return GUARDRAIL_FALLBACK_MSG

    try:
        # 1. 파이썬이 정확한 통계 계산
        start_time, end_time = parse_relative_datetime(question)
        err_cnt, warn_cnt = get_exact_log_counts(start_time, end_time)
        
        # 2. 벡터 검색 및 중복 제거된 컨텍스트 구성
        results = query_vectors(query_text=question, n_results=top_k, user_key=user_key, start_time=start_time, end_time=end_time)
        raw_docs = results[0] if results else []
        raw_metadatas = results[2] if results else []

        docs = []
        for doc, meta in zip(raw_docs, raw_metadatas):
            ts = meta.get('timestamp', 'N/A')
            cleaned_doc = doc.replace(f"[DATE: {ts}]", "").strip()
            docs.append(f"[DATE: {ts}] {cleaned_doc}")
            
        context_str = rerank_documents(query=question, documents=docs, top_k=2) if docs else "검색된 로그 없음."

        # 3. 데이터 주입 프롬프트 (강제 명령 버전)
        stats_injection = (
            f"[DATE]: {CURRENT_SYS_TIME}\n"
            "---[REQUIRED DATA: DO NOT CALCULATE]---\n"
            f"[STATS] ERROR: {err_cnt}, WARN: {warn_cnt}\n"
            "---------------------------------------\n"
            "- 위 [STATS] 값을 최우선 진실로 간주하고 답변에 그대로 인용할 것.\n"
            "- 컨텍스트 내 로그를 다시 세지 말 것. 오직 제공된 [STATS]만 사용할 것.\n"
            "- 날짜가 과거면 '과거 데이터'로 명시 후 현재와 구분할 것.\n\n"
        )

        final_question = f"{stats_injection}[분석할 현재 질문]\n{question}"
        
        prompt = RAG_PROMPT_TEMPLATE.format(
            current_date=CURRENT_SYS_TIME,
            context=context_str,
            question=final_question
        )

        # 4. Stateless 추론
        answer = await generate_completion(prompt)
        return postprocess_noun_ending(answer)

    except Exception as e:
        logger.error(f"RAG 추론 오류: {e}", exc_info=True)
        return "데이터 분석 중 기술적 오류가 발생함."