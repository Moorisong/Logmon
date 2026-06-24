# backend/llm/rag_engine.py
import logging
import sqlite3
import os
from typing import Tuple, Dict
from backend.db.chroma_handler import query_vectors
from backend.llm.client import generate_completion
from backend.llm.guardrail import check_guardrail, GUARDRAIL_FALLBACK_MSG
from backend.llm.utils import postprocess_noun_ending, parse_relative_datetime

logger = logging.getLogger(__name__)

def should_skip_rag(question: str) -> bool:
    """질문이 정량적인 통계/사실 확인 질문인지 판단하여 RAG 스킵 여부 결정"""
    keywords = ["몇 개", "몇 번", "횟수", "개수", "빈도", "순위", "어느", "시간대", "총", "합계", "얼마나"]
    return any(keyword in question for keyword in keywords)

def get_comprehensive_stats(start_time: str, end_time: str) -> Dict[str, str]:
    """모든 핵심 지표를 SQL로 미리 계산하여 리포트 형태로 반환합니다."""
    conn = sqlite3.connect(os.path.join(os.environ.get("LOGMON_DB_DIR", "/app/data"), "logmon.db"))
    cursor = conn.cursor()
    
    # 1. 코딩 몰입도
    cursor.execute("""
        SELECT 
            CASE WHEN file_path = 'UNKNOWN' THEN '기타(시스템 업데이트 이전)' ELSE file_path END as display_path, 
            COUNT(*) 
        FROM ide_activity_logs 
        WHERE workspace_active = 1 AND timestamp BETWEEN ? AND ? 
        GROUP BY file_path ORDER BY COUNT(*) DESC LIMIT 5
    """, (start_time, end_time))
    top_files = cursor.fetchall()
    coding_rep = "\n".join([f"- {f}: {c}회" for f, c in top_files]) if top_files else "활동 기록 없음"

    # 2. AI 활용도
    cursor.execute("""
        SELECT SUM(input_tokens + output_tokens), COUNT(*) 
        FROM ide_activity_logs 
        WHERE task_name = 'ai_assisted' AND timestamp BETWEEN ? AND ?
    """, (start_time, end_time))
    res = cursor.fetchone()
    ai_rep = f"- 총 활용 횟수: {res[1] or 0}회\n- 총 토큰 소모량: {res[0] or 0} tokens"

    # 3. 에러/디버깅
    cursor.execute("""
        SELECT event_type, COUNT(*) 
        FROM ide_activity_logs 
        WHERE event_type IN ('ERROR', 'WARN') AND timestamp BETWEEN ? AND ? 
        GROUP BY event_type
    """, (start_time, end_time))
    err_stats = cursor.fetchall()
    err_rep = "\n".join([f"- {e}: {c}회" for e, c in err_stats]) if err_stats else "에러/경고 기록 없음"

    # 4. 환경/IDE 사용 현황
    cursor.execute("""
        SELECT source_tool, COUNT(*) 
        FROM ide_activity_logs 
        WHERE timestamp BETWEEN ? AND ? 
        GROUP BY source_tool
    """, (start_time, end_time))
    ide_stats = cursor.fetchall()
    # [수정 완료]: ide_stats가 비어있는지 확인하도록 로직 수정
    ide_rep = "\n".join([f"- {i}: {c}건" for i, c in ide_stats]) if ide_stats else "정보 없음"

    conn.close()
    return {"coding": coding_rep, "ai": ai_rep, "error": err_rep, "ide": ide_rep}

async def ask_rag_agent(question: str, user_key: str, top_k: int = 5) -> str:
    if not check_guardrail(question): return GUARDRAIL_FALLBACK_MSG

    start_time, end_time = parse_relative_datetime(question)
    report = get_comprehensive_stats(start_time, end_time)
    
    # 2. 라우팅 로직: 통계 질문이면 RAG 스킵
    context_block = ""
    if not should_skip_rag(question):
        results = query_vectors(question, top_k, user_key, start_time, end_time)
        docs = [doc for res in (results or []) for doc in res if "[STATISTICS]" not in doc]
        if docs:
            context_block = f"\n[참고용 로그 문맥]\n{chr(10).join(docs[:3])}\n"

    # 3. 프롬프트 구성 (팩트 우선)
    prompt = f"""당신은 Logmon 수석 분석가입니다. 아래 [확정 리포트]를 근거로만 답변하십시오.

[확정 리포트]
---
1. 코딩 집중도 (상위 파일):
{report['coding']}

2. AI 도구 활용:
{report['ai']}

3. 에러 및 디버깅 현황:
{report['error']}

4. 개발 환경:
{report['ide']}
---
{context_block}
질문: {question}

지침:
1. 위 리포트에 기재된 수치가 가장 정확한 정답입니다.
2. 질문이 통계/수치와 관련된다면 리포트의 내용을 최우선으로 하십시오.
3. 한국어 명사형으로 간결하게 답변하십시오.
"""

    answer = await generate_completion(prompt)
    return postprocess_noun_ending(answer)