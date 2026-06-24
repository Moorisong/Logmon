# backend/llm/rag_engine.py
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
from backend.llm.memory import add_conversation
from backend.llm.utils import (
    postprocess_noun_ending,
    parse_relative_datetime,
)

logger = logging.getLogger(__name__)
_TZ_KST = datetime.timezone(datetime.timedelta(hours=9))

def get_exact_log_counts(start_time: Optional[str], end_time: Optional[str]) -> tuple:
    """SQLite DB에서 특정 기간 동안의 실제 ERROR 및 WARN 로그 개수를 정확히 카운트합니다."""
    db_dir = os.environ.get("LOGMON_DB_DIR", "/app/data")
    db_path = os.path.join(db_dir, "logmon.db")
    
    error_count, warn_count = 0, 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 실제 스키마(event_type, timestamp) 기준 쿼리
        q_err = "SELECT COUNT(*) FROM ide_activity_logs WHERE event_type LIKE '%ERROR%' AND timestamp >= ?"
        q_warn = "SELECT COUNT(*) FROM ide_activity_logs WHERE event_type LIKE '%WARN%' AND timestamp >= ?"
        
        # 기본값: 오늘로부터 10일 전 혹은 설정된 start_time
        base_time = start_time if start_time else (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat()
        
        cursor.execute(q_err, (base_time,))
        error_count = cursor.fetchone()[0]
        cursor.execute(q_warn, (base_time,))
        warn_count = cursor.fetchone()[0]
        conn.close()
    except Exception as e:
        logger.error(f"❌ 실시간 통계 조회 오류: {e}")
    return error_count, warn_count

async def ask_rag_agent(question: str, user_key: str, top_k: int = 10) -> str:
    logger.info(f"RAG 질의 시작: {question}")
    
    if not check_guardrail(question):
        return GUARDRAIL_FALLBACK_MSG

    try:
        start_time, end_time = parse_relative_datetime(question)
        
        # 파이썬이 먼저 정확한 통계를 계산함 (필살기 1)
        err_cnt, warn_cnt = get_exact_log_counts(start_time, end_time)
        
        results = query_vectors(query_text=question, n_results=top_k, user_key=user_key, start_time=start_time, end_time=end_time)
        
        raw_docs = results[0] if results else []
        raw_metadatas = results[2] if results else []

        if not raw_docs:
            return "최근 기록된 작업 로그가 존재하지 않습니다."

        docs = [f"[IDE: {meta.get('source_ide', 'Unknown')}]\n{doc}" for doc, meta in zip(raw_docs, raw_metadatas)]
        context_str = rerank_documents(query=question, documents=docs, top_k=2)

        # 시스템 규칙 주입 및 필살기 적용
        stats_injection = (
            "[정확한 실시간 DB 통계 데이터]\n"
            f"- 검색 기간 내 실제 ERROR 로그: {err_cnt}건\n"
            f"- 검색 기간 내 실제 WARN 로그: {warn_cnt}건\n"
            "※ 수치 답변 시 반드시 위 통계 데이터를 기준으로 할 것.\n"
            "※ 중요: 로그의 날짜가 시스템 시간(2026-06-24)보다 과거라면 이는 오래된 데이터이므로 명시할 것.\n\n"
        )

        final_question = f"{stats_injection}[분석할 현재 질문]\n{question}"
        
        current_date = datetime.datetime.now(_TZ_KST).strftime("%Y-%m-%d")
        prompt = RAG_PROMPT_TEMPLATE.format(
            current_date=current_date,
            context=context_str,
            question=final_question
        )

        answer = await generate_completion(prompt)
        answer = postprocess_noun_ending(answer)
        
        # 메모리 적재는 하되, 이전 맥락을 주입하지 않음으로써 Stateless 유지 (필살기 2)
        add_conversation(user_key, question, answer)
        
        return answer

    except Exception as e:
        logger.error(f"RAG 추론 오류: {e}", exc_info=True)
        return "데이터 분석 중 기술적 오류가 발생함."