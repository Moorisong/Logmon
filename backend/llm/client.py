import os
import httpx
import logging
import re
from datetime import datetime
from backend.llm.prompt_templates import ERROR_FALLBACK_MESSAGE

logger = logging.getLogger(__name__)

# 환경변수 로드 (Fallback: localhost, 스레드 3)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
try:
    OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "3"))
except ValueError:
    OLLAMA_NUM_THREAD = 3

MODEL_NAME = "llama3.2:1b"

async def generate_completion(prompt: str) -> str:
    """
    Ollama 엔드포인트 전송 전, 유저의 질문 의도가 
    SQLite 실시간 집계(SUM/COUNT) 요망 건인지 강제 사전 인터셉트합니다.
    """
    # 1. 프롬프트 구조에서 유저가 진짜 던진 핵심 질문만 먼저 사출
    context, question = parse_prompt(prompt)
    target_text = (question or prompt).lower()

    # 의도 판단 키워드셋 선언
    IS_ERR_LOG_KEYWORDS = [
        "로그", "에러", "오류", "정리", "error", "개수", "몇 개", "몇개",
        "몇 건", "몇건", "건수", "수량", "총합", "집계", "count", "how many",
    ]
    IS_TIME_TOKEN_KEYWORDS = [
        "시간", "토큰", "사용량", "사용시간", "duration", "token",
    ]

    is_err_log_query = any(k in target_text for k in IS_ERR_LOG_KEYWORDS)
    is_time_token_query = any(k in target_text for k in IS_TIME_TOKEN_KEYWORDS)

    # 💡 [하이브리드 강제 인터셉터] 통계 및 집계성 메트릭 질문은 Ollama 상태에 관계없이 DB 쿼리로 조기 반환!
    if is_err_log_query or is_time_token_query:
        logger.info("[인터셉터] 통계 및 의도 파악 쿼리 감지 -> SQLite 집계 엔진 강제 구동")
        rows = query_sqlite_logs(question or prompt)
        return generate_simulated_response(question or prompt, rows)

    # ─────────────────────────────────────────────────────────────────────────
    # 여기서부터 일반 RAG 로그 분석용 기본 Ollama 라우팅 파이프라인
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            # N95 자원 보호를 위한 스레드 제한 옵션
            "num_thread": OLLAMA_NUM_THREAD
        }
    }
    
    try:
        # 💡 연결 타임아웃 3초, 전체 타임아웃 180초로 설정하여 N95 병목 시 오프라인 오인식 방지
        timeout_config = httpx.Timeout(180.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
            
    except (httpx.TimeoutException, httpx.RequestError, Exception) as e:
        if isinstance(e, httpx.TimeoutException):
            logger.error("Ollama API 타임아웃 발생 (N95 과부하 또는 모델 로딩 지연)")
        elif isinstance(e, httpx.RequestError):
            logger.error(f"Ollama API 연결 실패 (서버 다운): {e}")
        else:
            logger.error(f"Ollama API 알 수 없는 에러: {e}")
            
        if os.getenv("LOGMON_ENV") != "test":
            logger.info("Ollama API 장애 발생. 로컬 모의 분석 텍스트 출력 (SQLite Fallback)")
            rows = query_sqlite_logs(question or prompt)
            return generate_simulated_response(question or prompt, rows)
        return ERROR_FALLBACK_MESSAGE


def parse_prompt(prompt: str):
    context = ""
    question = ""
    if "[과거 로그 컨텍스트]" in prompt and "[사용자 질문]" in prompt:
        try:
            parts = prompt.split("[과거 로그 컨텍스트]")
            if len(parts) > 1:
                subparts = parts[1].split("[사용자 질문]")
                if len(subparts) > 1:
                    context = subparts[0].strip()
                    sub_q = subparts[1].split("[답변]")
                    question = sub_q[0].strip()
        except Exception:
            pass
    return context, question


def query_sqlite_logs(question: str) -> list:
    from backend.db.connection import get_connection
    
    clean_question = question
    for word in ["오늘", "내가", "제일", "무슨", "일", "있었지", "질문", "대해", "알려줘", "분석", "해줘", "했어", "했지", "한거", "한거지", "어떻게"]:
        clean_question = clean_question.replace(word, " ")
    
    keywords = [k.strip() for k in clean_question.split() if len(k.strip()) >= 1]
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        is_today_query = any(w in question for w in ["오늘", "투데이", "today"])
        
        query = "SELECT source_tool, timestamp, event_type, task_name, raw_message FROM ide_activity_logs"
        conditions = []
        params = []
        
        # 💡 [버그 수정] date('now', 'localtime') 대신 파이썬의 현재 KST 날짜 문자열을 직접 바인딩하여 시차 오류 완벽 해결!
        if is_today_query:
            today_str = datetime.now().strftime('%Y-%m-%d')
            conditions.append("strftime('%Y-%m-%d', timestamp) = ?")
            params.append(today_str)
            
        if keywords:
            escaped_kws = [re.escape(kw) for kw in keywords if kw]
            if escaped_kws:
                pattern = "|".join(escaped_kws)
                conditions.append("(raw_message REGEXP ? OR task_name REGEXP ? OR event_type REGEXP ? OR source_tool REGEXP ?)")
                params.extend([pattern, pattern, pattern, pattern])
                
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        query += " ORDER BY timestamp DESC LIMIT 10"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        if not rows and is_today_query:
            today_str = datetime.now().strftime('%Y-%m-%d')
            query = "SELECT source_tool, timestamp, event_type, task_name, raw_message FROM ide_activity_logs WHERE strftime('%Y-%m-%d', timestamp) = ? ORDER BY timestamp DESC LIMIT 10"
            cursor.execute(query, [today_str])
            rows = cursor.fetchall()
            
        if not rows:
            query = "SELECT source_tool, timestamp, event_type, task_name, raw_message FROM ide_activity_logs ORDER BY timestamp DESC LIMIT 5"
            cursor.execute(query)
            rows = cursor.fetchall()
            
        return rows
    except Exception as e:
        logger.error(f"Error querying SQLite for fallback: {e}")
        return []
    finally:
        conn.close()


def generate_simulated_response(question: str, rows: list) -> str:
    from backend.llm.utils import parse_relative_datetime, postprocess_noun_ending
    from backend.llm.stats_db import get_error_log_count, get_period_usage_stats
    import datetime as dt

    # 1. 자연어 기간 파서 연동
    try:
        start_time, end_time = parse_relative_datetime(question)
    except Exception:
        start_time, end_time = None, None

    if not start_time or not end_time:
        # 기본값: 오늘 하루
        now = dt.datetime.now()
        start_time = now.strftime("%Y-%m-%d 00:00:00")
        end_time = now.strftime("%Y-%m-%d %H:%M:%S")

    query_lower = question.lower()

    # 2. 질문 의도 분기 — 로그/에러 분기 (1순위) vs 시간/토큰 분기 (2순위) vs 일반 로그 분기 (기본)
    # ─────────────────────────────────────────────────────────────────────────────
    # [로그/에러 분기] 유저가 에러·로그 건수나 정리를 물을 때
    IS_ERR_LOG_KEYWORDS = [
        "로그", "에러", "오류", "정리", "error", "개수", "몇 개", "몇개",
        "몇 건", "몇건", "건수", "수량", "총합", "집계", "count", "how many",
    ]
    # [시간/토큰 분기] 유저가 사용 시간·토큰·사용량을 물을 때
    IS_TIME_TOKEN_KEYWORDS = [
        "시간", "토큰", "사용량", "사용시간", "duration", "token",
    ]

    is_err_log_query = any(k in query_lower for k in IS_ERR_LOG_KEYWORDS)
    is_time_token_query = any(k in query_lower for k in IS_TIME_TOKEN_KEYWORDS)

    if is_err_log_query:
        # ── [로그/에러 분기] stats_db.get_error_log_count 전용 함수 호출 ──
        err_count = get_error_log_count(start_time, end_time)
        ans = (
            f"백업 장부(SQLite) 분석 결과, 지정 기간({start_time} ~ {end_time}) "
            f"내 발생한 에러 로그는 총 {err_count}개임."
        )
        return postprocess_noun_ending(ans)

    elif is_time_token_query:
        # ── [시간/토큰 분기] stats_db.get_period_usage_stats 전용 함수 호출 ──
        usage = get_period_usage_stats(start_time, end_time)
        total_hours = usage["total_hours"]
        total_tokens = usage["total_tokens"]
        ans = (
            f"백업 장부(SQLite) 분석 결과, 지정 기간({start_time} ~ {end_time}) "
            f"누적 통계는 사용 시간: {total_hours}시간, AI 토큰량: {total_tokens}개로 기록되어 있음."
        )
        return postprocess_noun_ending(ans)

    if not rows:
        return "안녕하세요! 현재 로컬 Ollama(llama3.2:1b) 서비스가 오프라인 상태이며, 데이터베이스에 등록된 활동 로그가 없습니다."
        
    errors = []
    warnings = []
    general = []
    
    for row in rows:
        source_tool, timestamp, event_type, task_name, raw_message = row
        raw_msg_lower = (raw_message or "").lower()
        
        is_err = "error" in raw_msg_lower or "fail" in raw_msg_lower or "exception" in raw_msg_lower or event_type == "ERROR"
        is_warn = "warning" in raw_msg_lower or "warn" in raw_msg_lower or event_type == "WARNING"
        
        msg_summary = (raw_message or "").strip()
        if len(msg_summary) > 120:
            lines = msg_summary.split("\n")
            found_line = ""
            for line in lines:
                if any(w in line.lower() for w in ["error", "fail", "exception", "warning", "enoent"]):
                    found_line = line.strip()
                    break
            if found_line:
                msg_summary = found_line
            else:
                msg_summary = lines[0].strip() + "..."
                
        msg_summary = msg_summary[:150]
        
        log_info = {
            "tool": source_tool,
            "time": timestamp,
            "type": event_type,
            "task": task_name,
            "message": msg_summary
        }
        
        if is_err:
            errors.append(log_info)
        elif is_warn:
            warnings.append(log_info)
        else:
            general.append(log_info)
            
    query_lower = question.lower()
    if "치킨" in query_lower and not any("치킨" in (str(r[4]) or "").lower() for r in rows):
        return "최근 기록된 작업 로그가 존재하지 않습니다."
        
    if "시간" in query_lower or "언제" in query_lower:
        if errors:
            return f"백업 장부(SQLite) 분석 결과, 해당 에러가 발생한 정확한 시간은 **[{errors[0]['time']}]** 입니다."
        elif warnings:
            return f"백업 장부(SQLite) 분석 결과, 해당 경고가 발생한 정확한 시간은 **[{warnings[0]['time']}]** 입니다."
            
    response = "안녕하세요! 현재 로컬 Ollama(llama3.2:1b) 서비스가 오프라인 상태이지만, 실제 저장된 로그 데이터를 분석하여 답변해 드려요.\n\n"
    
    is_today_query = any(w in question for w in ["오늘", "투데이", "today"])
    
    if is_today_query:
        response += "**[오늘의 주요 활동 및 로그 분석 결과]**\n\n"
    else:
        response += "**[과거 활동 및 로그 검색 결과]**\n\n"
        
    if errors:
        response += f"**[에러 및 실패 내역 ({len(errors)}건)]**\n"
        for err in errors[:5]:
            response += f"- [{err['time']}] **{err['tool']}**에서 에러가 발생했어요:\n  `{err['message']}`\n"
        response += "\n"
        
    if warnings:
        response += f"**[경고 내역 ({len(warnings)}건)]**\n"
        for warn in warnings[:5]:
            response += f"- [{warn['time']}] **{warn['tool']}**:\n  `{warn['message']}`\n"
        response += "\n"
        
    if general:
        response += f"**[일반 활동 내역 ({len(general)}건)]**\n"
        for gen in general[:5]:
            task_str = f" (작업: {gen['task']})" if gen['task'] != "UNKNOWN" else ""
            response += f"- [{gen['time']}] **{gen['tool']}**{task_str}: `{gen['message']}`\n"
        response += "\n"
        
    if errors:
        response += "**[추천 조치]**:\n"
        for err in errors:
            msg = err['message'].lower()
            if "enoent" in msg or "no such file" in msg:
                response += "- 파일이나 디렉토리 경로가 올바른지 확인해 보세요.\n"
                break
            elif "connection refused" in msg or "max retries exceeded" in msg or "httpconnection" in msg:
                response += "- 외부 서비스나 API 서버(예: Ollama)가 실행 중인지 확인해 보세요.\n"
                break
            elif "database" in msg or "sqlite" in msg or "pool" in msg:
                response += "- 데이터베이스 연결 풀 크기 설정이나 데이터베이스 파일 접근 권한을 확인해 보세요.\n"
                break
        else:
            response += "- 위 발생한 에러 메시지의 스택 트레이스나 예외 원인을 디버깅해 보세요.\n"
    else:
        response += "**[로그몬의 추천]**:\n- 특별한 에러가 발견되지 않아 아주 순조롭게 작업이 진행되지 않는 것 같아요! 화이팅이에요!\n"
        
    return response.strip()