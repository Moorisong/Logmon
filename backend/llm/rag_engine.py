import logging
import sqlite3
import os
from typing import Tuple
from backend.db.chroma_handler import query_vectors
from backend.llm.client import generate_completion
from backend.llm.prompt_templates import RAG_PROMPT_TEMPLATE
from backend.llm.guardrail import check_guardrail, GUARDRAIL_FALLBACK_MSG
from backend.llm.reranker import rerank_documents
from backend.llm.utils import postprocess_noun_ending, parse_relative_datetime

logger = logging.getLogger(__name__)
CURRENT_SYS_TIME = "2026-06-24"

def get_stats_data(start_time: str, end_time: str) -> Tuple[int, int, str]:
    """에러 총계와 날짜별 상세 통계를 반환합니다."""
    conn = sqlite3.connect(os.path.join(os.environ.get("LOGMON_DB_DIR", "/app/data"), "logmon.db"))
    cursor = conn.cursor()
    
    # 총계
    cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE raw_message LIKE '%[error]%' AND timestamp BETWEEN ? AND ?", (start_time, end_time))
    err = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE raw_message LIKE '%[warning]%' AND timestamp BETWEEN ? AND ?", (start_time, end_time))
    warn = cursor.fetchone()[0]
    
    # 날짜별 통계 (LLM이 답변할 수 있게 함)
    cursor.execute("""
        SELECT date(timestamp), COUNT(*) 
        FROM ide_activity_logs 
        WHERE raw_message LIKE '%[error]%' AND timestamp BETWEEN ? AND ? 
        GROUP BY date(timestamp) 
        ORDER BY date(timestamp) DESC
    """, (start_time, end_time))
    daily_stats = cursor.fetchall()
    
    table_str = "\n".join([f"- {d}: {c}회" for d, c in daily_stats])
    conn.close()
    return err, warn, table_str

async def ask_rag_agent(question: str, user_key: str, top_k: int = 5) -> str:
    if not check_guardrail(question): return GUARDRAIL_FALLBACK_MSG

    start_time, end_time = parse_relative_datetime(question)
    err_cnt, warn_cnt, daily_table = get_stats_data(start_time, end_time)
    
    # 벡터 검색 (통계 로그 방해 금지: 통계 텍스트가 포함된 로그는 필터링)
    results = query_vectors(question, top_k, user_key, start_time, end_time)
    docs = []
    if results and results[0]:
        for doc in results[0]:
            if "[STATISTICS]" not in doc: # 방해물 제거
                docs.append(doc)
    
    context_str = "\n".join(docs[:3]) if docs else "검색된 로그 없음."

    # 프롬프트: 확실한 팩트 주입
    prompt = (
        f"당신은 분석가입니다. [확정 데이터]를 근거로만 답변하십시오.\n\n"
        f"[확정 데이터]\n"
        f"- 기간: {start_time} ~ {end_time}\n"
        f"- 에러 총 횟수: {err_cnt}회\n"
        f"- 날짜별 에러 상세:\n{daily_table}\n\n"
        f"[참고용 컨텍스트]\n{context_str}\n\n"
        f"질문: {question}\n\n"
        f"지침:\n1. [확정 데이터]가 정답입니다. 컨텍스트 속 수치는 무시하십시오.\n"
        f"2. 0건이면 '없음'으로 답변하십시오.\n"
        f"3. 가장 많은 날짜를 물으면 [확정 데이터]의 '날짜별 에러 상세'를 확인해 대답하십시오.\n"
        f"4. 한국어 명사형으로 간결하게 답변하십시오."
    )

    answer = await generate_completion(prompt)
    return postprocess_noun_ending(answer)