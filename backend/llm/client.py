import os
import httpx
import logging
import re
from datetime import datetime
from backend.llm.prompt_templates import ERROR_FALLBACK_MESSAGE

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://logmon-ollama:11434")
try:
    OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "2")) # N95 서버 안정성을 위해 스레드 2로 제한
except ValueError:
    OLLAMA_NUM_THREAD = 2

MODEL_NAME = "llama3.2:1b"

# [교정] 검증된 도커 내부의 찐 데이터베이스 금고 절대 경로로 통일
REAL_DB_PATH = "/app/data/logmon.db"

async def generate_completion(prompt: str) -> str:
    """Ollama 전송 전 핵심 집계 쿼리 여부를 선제 인터셉트합니다."""
    context, question = parse_prompt(prompt)

    if question:
        # 겹치지 않게 명확하게 격리한 키워드셋
        IS_ERR_LOG_KEYWORDS = ["에러", "오류", "error", "critical"]
        IS_TIME_TOKEN_KEYWORDS = ["시간", "토큰", "사용량", "사용시간", "duration", "token", "얼마나"]
        IS_TOTAL_LOG_KEYWORDS = ["몇 개", "몇개", "건수", "수량", "총합", "집계", "count", "전체", "활동", "작업", "로그 개수"]

        q_lower = question.lower()
        is_err_log_query = any(k in q_lower for k in IS_ERR_LOG_KEYWORDS)
        is_time_token_query = any(k in q_lower for k in IS_TIME_TOKEN_KEYWORDS)
        is_total_log_query = any(k in q_lower for k in IS_TOTAL_LOG_KEYWORDS)

        # 라우팅 우선순위 철저 정렬 (시간 -> 에러 -> 전체개수)
        if is_time_token_query:
            logger.info("[인터셉터] 1순위: 시간 및 토큰 누적 통계 분기 가동")
            rows = query_sqlite_logs(question)
            return generate_simulated_response(question, rows)
            
        elif is_err_log_query:
            logger.info("[인터셉터] 2순위: 에러 명시 질의 분기 가동")
            rows = query_sqlite_logs(question)
            return generate_simulated_response(question, rows)
            
        elif is_total_log_query:
            logger.info("[인터셉터] 3순위: 전체 활동 로그 수량 분기 가동")
            rows = query_sqlite_logs(question)
            return generate_simulated_response(question, rows)

    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_thread": OLLAMA_NUM_THREAD,
            "stop": ["<start_of_turn>", "<end_of_turn>", "\n\n"]
        }
    }
    
    try:
        timeout_config = httpx.Timeout(180.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
    except Exception as e:
        logger.error(f"Ollama 본진 통신 실패 (Fallback 구동): {e}")
        safe_question = question if question else ""
        rows = query_sqlite_logs(safe_question) if safe_question else []
        return generate_simulated_response(safe_question, rows)


def parse_prompt(prompt: str) -> tuple:
    context, question = "", ""
    if "[User Query]" in prompt:
        try:
            after_query = prompt.split("[User Query]")[1]
            question = after_query.split("<end_of_turn>")[0].strip()
            if "[Context]" in prompt:
                context = prompt.split("[Context]")[1].split("[User Query]")[0].strip()
        except Exception: pass
    return context, question


def query_sqlite_logs(question: str) -> list:
    import sqlite3
    try:
        # [교정] 가짜 깡통 경로 걷어내고 찐 금고 오픈
        conn = sqlite3.connect(REAL_DB_PATH)
        cursor = conn.cursor()
        is_today_query = any(w in question for w in ["오늘", "투데이", "today"])
        query = "SELECT source_tool, timestamp, event_type, task_name, raw_message FROM ide_activity_logs"
        conditions = []
        
        if is_today_query:
            conditions.append("date(timestamp) = date('now', 'localtime')")
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC LIMIT 10"
        
        cursor.execute(query)
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"SQLite 조회 에러: {e}")
        return []
    finally:
        try: conn.close()
        except: pass


def generate_simulated_response(question: str, rows: list) -> str:
    """장부 데이터를 기반으로 오차 없는 정확한 숏폼 정답을 바인딩합니다."""
    from backend.llm.utils import parse_relative_datetime, postprocess_noun_ending
    from backend.llm.stats_db import get_error_log_count, get_period_usage_stats
    import sqlite3
    import datetime as dt

    try:
        start_time, end_time = parse_relative_datetime(question)
    except Exception:
        start_time, end_time = None, None

    if not start_time or not end_time:
        now = dt.datetime.now()
        start_time = now.strftime("%Y-%m-%d 00:00:00")
        end_time = now.strftime("%Y-%m-%d %H:%M:%S")

    query_lower = question.lower()

    IS_ERR_LOG_KEYWORDS = ["에러", "오류", "error", "critical"]
    IS_TIME_TOKEN_KEYWORDS = ["시간", "토큰", "사용량", "사용시간", "duration", "token", "얼마나"]
    IS_TOTAL_LOG_KEYWORDS = ["몇 개", "몇개", "건수", "수량", "총합", "집계", "count", "전체", "활동", "작업", "로그 개수"]

    is_err_log_query = any(k in query_lower for k in IS_ERR_LOG_KEYWORDS)
    is_time_token_query = any(k in query_lower for k in IS_TIME_TOKEN_KEYWORDS)
    is_total_log_query = any(k in query_lower for k in IS_TOTAL_LOG_KEYWORDS)

    # 1순위: 순수 시간 및 토큰 누적 통계 분기
    if is_time_token_query:
        usage = get_period_usage_stats(start_time, end_time)
        total_hours = usage["total_hours"]
        total_tokens = usage["total_tokens"]
        ans = f"백업 장부(SQLite) 분석 결과, 지정 기간({start_time} ~ {end_time}) 누적 통계는 사용 시간: {total_hours}시간, AI 토큰량: {total_tokens}개로 기록되어 있음."
        return postprocess_noun_ending(ans)

    # 2순위: 에러 명시 질의 분기
    elif is_err_log_query:
        err_count = get_error_log_count(start_time, end_time)
        ans = f"백업 장부(SQLite) 분석 결과, 지정 기간({start_time} ~ {end_time}) 내 발생한 에러 로그는 총 {err_count}개임."
        return postprocess_noun_ending(ans)

    # 3순위: 개수/수량/전체 장부 질의 분기
    elif is_total_log_query:
        import sqlite3
        # [교정] 내부 카운트 연산도 찐 금고 경로에서 집계하도록 강제 매핑
        conn = sqlite3.connect(REAL_DB_PATH)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE timestamp BETWEEN ? AND ? AND task_name != 'STATISTICS'", (start_time, end_time))
            total_count = cursor.fetchone()[0] or 0
        finally:
            conn.close()
        ans = f"백업 장부(SQLite) 분석 결과, 지정 기간({start_time} ~ {end_time}) 내 유입된 실제 전체 활동 로그 개수는 총 {total_count}개임."
        return postprocess_noun_ending(ans)

    return "안녕하세요! 상세 로그 분석을 원하시면 '에러 개수', '전체 로그 몇개', '사용 시간' 등 명확한 키워드로 질문해 요망."