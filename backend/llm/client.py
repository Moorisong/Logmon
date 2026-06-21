import os
import httpx
import logging
from backend.llm.prompt_templates import ERROR_FALLBACK_MESSAGE

logger = logging.getLogger(__name__)

# 환경변수 로드 (Fallback: localhost, 스레드 3)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
try:
    OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "3"))
except ValueError:
    OLLAMA_NUM_THREAD = 3

MODEL_NAME = "gemma2:2b"

async def generate_completion(prompt: str) -> str:
    """
    Ollama /api/generate 엔드포인트에 비동기로 프롬프트를 전송하고 
    단일 문자열 응답을 받아옵니다. (스트리밍은 MVP 복잡성 방지를 위해 제외)
    """
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
        # 타임아웃 30초 설정 (저전력 CPU 응답 지연 대비)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
            
    except httpx.TimeoutException:
        logger.error("Ollama API 타임아웃 발생 (N95 과부하 또는 모델 로딩 지연)")
        return ERROR_FALLBACK_MESSAGE
    except httpx.RequestError as e:
        logger.error(f"Ollama API 연결 실패 (서버 다운): {e}")
        # 로컬 개발 환경(LOGMON_ENV가 test가 아님)일 경우 대화 테스트 흐름을 매끄럽게 만들기 위해 모의 응답 시뮬레이션 적용
        if ("localhost" in OLLAMA_HOST or "127.0.0.1" in OLLAMA_HOST) and os.getenv("LOGMON_ENV") != "test":
            logger.info("Ollama API 미작동으로 인한 로컬 모의 분석 텍스트 출력")
            context, question = parse_prompt(prompt)
            rows = query_sqlite_logs(question or prompt)
            return generate_simulated_response(question or prompt, rows)
        return ERROR_FALLBACK_MESSAGE
    except Exception as e:
        logger.error(f"Ollama API 알 수 없는 에러: {e}")
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
        
        if is_today_query:
            conditions.append("date(timestamp) = date('now', 'localtime')")
            
        if keywords:
            keyword_conditions = []
            for kw in keywords:
                keyword_conditions.append("(raw_message LIKE ? OR task_name LIKE ? OR event_type LIKE ? OR source_tool LIKE ?)")
                like_pat = f"%{kw}%"
                params.extend([like_pat, like_pat, like_pat, like_pat])
            if keyword_conditions:
                conditions.append("(" + " OR ".join(keyword_conditions) + ")")
                
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        query += " ORDER BY timestamp DESC LIMIT 10"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        if not rows and is_today_query:
            query = "SELECT source_tool, timestamp, event_type, task_name, raw_message FROM ide_activity_logs WHERE date(timestamp) = date('now', 'localtime') ORDER BY timestamp DESC LIMIT 10"
            cursor.execute(query)
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
    if not rows:
        return "안녕하세요! 현재 로컬 Ollama(gemma2:2b) 서비스가 오프라인 상태이며, 데이터베이스에 등록된 활동 로그가 없습니다."
        
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
            
    response = "안녕하세요! 현재 로컬 Ollama(gemma2:2b) 서비스가 오프라인 상태이지만, 실제 저장된 로그 데이터를 분석하여 답변해 드려요.\n\n"
    
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
        response += "**[로그몬의 추천]**:\n- 특별한 에러가 발견되지 않아 아주 순조롭게 작업이 진행되고 있는 것 같아요! 화이팅이에요!\n"
        
    return response.strip()

