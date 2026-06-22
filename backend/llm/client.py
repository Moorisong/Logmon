import os
import httpx
import logging
import re
from datetime import datetime
import sqlite3
from backend.llm.prompt_templates import ERROR_FALLBACK_MESSAGE

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://logmon-ollama:11434")
try:
    OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "2"))
except ValueError:
    OLLAMA_NUM_THREAD = 2

MODEL_NAME = "llama3.2:1b"

# [교정] 검증된 도커 내부의 찐 데이터베이스 금고 절대 경로로 철저히 통일
REAL_DB_PATH = "/app/data/logmon.db"

async def generate_completion(prompt: str) -> str:
    """Ollama 전송 전 핵심 집계 쿼리 여부를 선제 인터셉트합니다."""
    context, question = parse_prompt(prompt)

    if question:
        IS_ERR_LOG_KEYWORDS = ["에러", "오류", "error", "critical"]
        IS_TIME_TOKEN_KEYWORDS = ["시간", "토큰", "사용량", "사용시간", "duration", "token", "얼마나"]
        IS_TOTAL_LOG_KEYWORDS = ["몇 개", "몇개", "건수", "수량", "총합", "집계", "count", "전체", "활동", "작업", "로그 개수"]

        q_lower = question.lower()
        is_err_log_query = any(k in q_lower for k in IS_ERR_LOG_KEYWORDS)
        is_time_token_query = any(k in q_lower for k in IS_TIME_TOKEN_KEYWORDS)
        is_total_log_query = any(k in q_lower for k in IS_TOTAL_LOG_KEYWORDS)

        # 라우팅 우선순위 정렬
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
    try:
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
    """외부 야바위 모듈 의존성을 파괴하고, 내부에서 찐 금고 쿼리를 다이렉트로 때려박습니다."""
    from backend.llm.utils import parse_relative_datetime, postprocess_noun_ending
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

    # 1순위: 사용 시간 및 토큰 (내부 다이렉트 집계로 야바위 원천 차단)
    if is_time_token_query:
        conn = sqlite3.connect(REAL_DB_PATH)
        try:
            cursor = conn.cursor()
            # 토큰 합산 쿼리 직접 가동
            cursor.execute("SELECT raw_message FROM ide_activity_logs WHERE timestamp BETWEEN ? AND ?", (start_time, end_time))
            token_rows = cursor.fetchall()
            total_tokens = 0
            for r in token_rows:
                msg = r[0] or ""
                p_match = re.search(r'"prompt_tokens"\s*:\s*(\d+)', msg)
                c_match = re.search(r'"completion_tokens"\s*:\s*(\d+)', msg)
                if p_match: total_tokens += int(p_match.group(1))
                if c_match: total_tokens += int(c_match.group(1))
            
            # 대략적인 시간 추산 (로그가 찍힌 첫 시간과 마지막 시간 차이 계산)
            cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM ide_activity_logs WHERE timestamp BETWEEN ? AND ?", (start_time, end_time))
            min_t, max_t = cursor.fetchone()
            total_hours = 0.0
            if min_t and max_t:
                try:
                    d1 = dt.datetime.strptime(min_t.split(".")[0], "%Y-%m-%d %H:%M:%S")
                    d2 = dt.datetime.strptime(max_t.split(".")[0], "%Y-%m-%d %H:%M:%S")
                    total_hours = round((d2 - d1).total_seconds() / 3600.0, 1)
                except: pass
        finally:
            conn.close()
        ans = f"백업 장부(SQLite) 분석 결과, 지정 기간({start_time} ~ {end_time}) 누적 통계는 사용 시간: {total_hours}시간, AI 토큰량: {total_tokens}개로 기록되어 있음."
        return postprocess_noun_ending(ans)

    # 2순위: 에러 명시 질의 분기 (stats_db 버리고 직접 쿼리 수행)
    elif is_err_log_query:
        conn = sqlite3.connect(REAL_DB_PATH)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE timestamp BETWEEN ? AND ? AND event_type = 'ERROR'", (start_time, end_time))
            err_count = cursor.fetchone()[0] or 0
        finally:
            conn.close()
        ans = f"백업 장부(SQLite) 분석 결과, 지정 기간({start_time} ~ {end_time}) 내 발생한 에러 로그는 총 {err_count}개임."
        return postprocess_noun_ending(ans)

    # 3순위: 개수/수량/전체 장부 질의 분기
    elif is_total_log_query:
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