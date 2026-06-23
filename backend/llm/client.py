# backend/llm/client.py
import os
import httpx
import logging
import re
import sqlite3

from backend.llm.router import (
    detect_fast_track,
    build_llm_fallback_prompt,
    parse_llm_filter_response,
    ROUTE_FAST_TRACK,
)
from backend.llm.fact_reporters import (
    get_fact_token_report,
    get_fact_warning_report,
    get_fact_error_report,
    get_fact_activity_summary,
    get_fact_ide_uptime,
    get_fact_git_summary,
    get_fact_network_db_errors,
)
from backend.llm.simulated_response import query_sqlite_logs, generate_simulated_response

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://logmon-ollama:11434")
try:
    OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "3"))
except ValueError:
    OLLAMA_NUM_THREAD = 3

MODEL_NAME = os.getenv("LLM_MODEL", "llama3.2:1b")
REAL_DB_PATH = "/app/data/logmon.db"

# Fast-track route_key → 팩트 함수 매핑 테이블
_FAST_TRACK_DISPATCH = {
    "token":        lambda: get_fact_token_report(),
    "warning":      lambda: get_fact_warning_report(),
    "error":        lambda: get_fact_error_report(),
    "activity":     lambda: get_fact_activity_summary(),
    "ide_uptime": lambda: get_fact_ide_uptime(),
    "git":          lambda: get_fact_git_summary(),
    "network_db": lambda: get_fact_network_db_errors(),
}


def get_db_connection():
    return sqlite3.connect(f"file:{REAL_DB_PATH}?mode=ro", uri=True, timeout=30.0)


async def generate_completion(prompt: str) -> str:
    """
    메인 LLM 생성 함수.
    1. 최신 질문 추출 및 대화 이력 분리
    2. Hybrid Router로 Fast-track / LLM Fallback 분기
    3. Fast-track: DB 팩트 함수 즉시 반환
    4. LLM Fallback: Ollama 호출 (오프라인 시 환경별 Fallback)
    """
    logger.info(f"=== [디버깅] 백엔드 유입 원본 프롬프트 ===\n{prompt}\n====================================")

    latest_query, history_context = parse_vacuum_clean_query(prompt)
    logger.info(f"[파싱 완료] 최신 질문: '{latest_query}'")

    # Fast-track 라우팅 시도
    fast_result = detect_fast_track(latest_query)
    if fast_result and fast_result.route == ROUTE_FAST_TRACK:
        handler = _FAST_TRACK_DISPATCH.get(fast_result.fast_track_key)
        if handler:
            return handler()

    # 상세 분석 / IDE 정보 등 LLM 컨텍스트 추론
    if re.search(r"(상세|정리|종류|내용|어떤|이유|왜|분석|목록|패턴|알려줘|어때|개선|어떻게|설명)", latest_query.lower()):
        target_type = (
            "error" if any(x in latest_query.lower() for x in ["에러", "오류"])
            else "warn" if "경고" in latest_query.lower()
            else "general"
        )
        return await call_ollama_with_context(latest_query, history_context, target_type)

    # LLM Fallback: Ollama 호출
    return await call_ollama_with_context(latest_query, history_context, "general")


async def extract_llm_filters(question: str) -> dict:
    """
    LLM을 호출하여 질문에서 ChromaDB 필터 조건을 추출합니다.
    Ollama 연결 실패 시 빈 dict를 안전하게 반환합니다.
    """
    prompt = build_llm_fallback_prompt(question)
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json", # ◀ [핵심 수정] 가벼운 모델이 JSON 형식을 깨뜨리지 못하도록 Ollama API 차원에서 강제합니다.
        "options": {"temperature": 0.0, "num_thread": OLLAMA_NUM_THREAD},
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, json=payload)
            raw_text = response.json().get("response", "")
            
            # 모델이 완전히 빈 응답을 반환할 경우를 대비한 방어 로직
            if not raw_text.strip():
                return {}
                
            return parse_llm_filter_response(raw_text)
    except Exception as e:
        logger.warning(f"[Router] LLM 필터 추출 실패 (Fallback: 빈 필터 사용): {e}")
        return {}


async def call_ollama_with_context(
    latest_query: str, history_context: str, target_type: str
) -> str:
    db_context = _fetch_db_context(target_type)

    system_prompt = f"""당신은 Logmon AI, 시스템 로그 분석 어시스턴트입니다.
[이전 대화 기록]을 통해 현재 대화의 맥락(사용자가 지칭하는 에러나 경고 등)을 반드시 파악하세요.
[컨텍스트 데이터]가 있다면 참고하고, 최종적으로 오직 [최신 질문]에 대해서만 명확하고 간결하게 답변하세요.

[이전 대화 기록]
{history_context if history_context else "이전 대화 없음."}

[컨텍스트 데이터 (최신 DB 조회결과)]
{db_context}
"""

    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {
        "model": MODEL_NAME,
        "prompt": f"{system_prompt}\n\n최신 질문: {latest_query}",
        "stream": False,
        "options": {"temperature": 0.3, "num_thread": OLLAMA_NUM_THREAD},
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(endpoint, json=payload)
            return response.json().get("response", "데이터 분석 완료.")
    except Exception as ollama_err:
        logmon_env = os.getenv("LOGMON_ENV", "prod")
        if logmon_env == "test":
            from backend.llm.prompt_templates import ERROR_FALLBACK_MESSAGE
            return ERROR_FALLBACK_MESSAGE
        # dev/prod: SQLite 기반 모의 응답으로 Graceful Degradation
        logger.warning(f"[Ollama 오프라인] Fallback 활성화: {ollama_err}")
        return generate_simulated_response(latest_query, query_sqlite_logs(latest_query))


def _fetch_db_context(target_type: str) -> str:
    """target_type에 따라 DB에서 컨텍스트를 조회하여 문자열로 반환합니다."""
    try:
        with get_db_connection() as conn:
            if target_type == "ide_info":
                rows = conn.execute(
                    "SELECT source_tool, raw_message FROM ide_activity_logs "
                    "WHERE source_tool LIKE '%IDE%' OR raw_message LIKE '%IDE%' LIMIT 20"
                ).fetchall()
                return "IDE 로그:\n" + "\n".join([f"- {r[0]}: {r[1][:100]}" for r in rows]) if rows else "관련 데이터 없음."
            elif target_type == "warn":
                rows = conn.execute(
                    "SELECT raw_message FROM ide_activity_logs WHERE raw_message LIKE '%warn%' LIMIT 10"
                ).fetchall()
                return "경고 로그:\n" + "\n".join([f"- {r[0][:150]}" for r in rows]) if rows else "관련 데이터 없음."
            elif target_type == "error":
                rows = conn.execute(
                    "SELECT raw_message FROM ide_activity_logs WHERE raw_message LIKE '%error%' LIMIT 10"
                ).fetchall()
                return "에러 로그:\n" + "\n".join([f"- {r[0][:150]}" for r in rows]) if rows else "관련 데이터 없음."
            else:
                rows = conn.execute(
                    "SELECT source_tool, raw_message FROM ide_activity_logs ORDER BY rowid DESC LIMIT 5"
                ).fetchall()
                return "최근 활동 로그:\n" + "\n".join([f"- {r[0]}: {r[1][:100]}" for r in rows]) if rows else "관련 데이터 없음."
    except Exception:
        return "DB 조회 실패"


def parse_vacuum_clean_query(prompt: str) -> tuple:
    """
    프론트엔드에서 넘어온 전체 텍스트에서 '최신 질문'을 분리하고,
    과거 유저-AI 대화 3턴을 유지하여 문맥으로 묶어냅니다.
    """
    clean_q = prompt.replace('"', "").replace("'", "")

    if re.search(r"user avatar", clean_q, re.IGNORECASE):
        blocks = re.split(r"(?i)user avatar", clean_q)
        latest_raw = blocks[-1]
        latest_query = re.split(r"(?i)assistant avatar", latest_raw)[0].strip()
        history_lines = []
        for block in blocks[:-1]:
            if not block.strip():
                continue
            parts = re.split(r"(?i)assistant avatar", block)
            user_text = parts[0].strip()
            if user_text:
                history_lines.append(f"사용자: {user_text}")
            if len(parts) > 1:
                ai_text = parts[1].strip()
                if ai_text:
                    history_lines.append(f"AI: {ai_text}")
        history = "\n\n".join(history_lines[-6:])
        return latest_query, history

    blocks = re.split(r"\[User Query\]|<start_of_turn>user", clean_q)
    raw_latest_block = blocks[-1]

    if "[현재 질문]" in raw_latest_block:
        latest_query = raw_latest_block.split("[현재 질문]")[-1]
    else:
        latest_query = raw_latest_block

    latest_query = re.sub(r"<start_of_turn>model|<end_of_turn>", "", latest_query).strip()
    history = "\n".join([b[:200] for b in blocks[-4:-1] if b.strip()])
    return latest_query, history