import os
import httpx
import logging
import re
import sqlite3

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://logmon-ollama:11434")
try:
    OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "3"))
except ValueError:
    OLLAMA_NUM_THREAD = 3

# ◀ [완벽 수정] gemma의 흔적을 완전히 지우고 llama3.2:1b를 기본값으로 설정
MODEL_NAME = os.getenv("LLM_MODEL", "llama3.2:1b")
REAL_DB_PATH = "/app/data/logmon.db"

def get_db_connection():
    return sqlite3.connect(f"file:{REAL_DB_PATH}?mode=ro", uri=True, timeout=30.0)

async def generate_completion(prompt: str) -> str:
    # 🎯 1. 최신 질문(라우팅용)과 과거 대화 기록(문맥 유지용) 분리 추출
    latest_query, history_context = parse_vacuum_clean_query(prompt)
    q_lower = latest_query.lower()
    
    logger.info(f"[파싱 완료] 최신 질문: '{latest_query}'")
    
    # 🎯 2. 라우팅 분기 (최신 질문 기준)
    # IDE 정보 확인
    if re.search(r'\b(ide|에디터|프로그램|종류)\b', q_lower):
        return await call_ollama_with_context(latest_query, history_context, "ide_info")

    # 상세 분석, 설명, 개선 요청 (대화형 추론)
    if re.search(r'(상세|정리|종류|내용|어떤|이유|왜|분석|목록|패턴|알려줘|어때|개선|어떻게|설명)', q_lower):
        target_type = "error" if any(x in q_lower for x in ["에러", "오류"]) else "warn" if "경고" in q_lower else "general"
        return await call_ollama_with_context(latest_query, history_context, target_type)
        
    # 단순 통계/개수 확인 (이때는 DB 결과만 바로 리턴)
    if re.search(r'\b(토큰|token)\b', q_lower): return get_fact_token_report()
    if re.search(r'\b(경고|warn)\b', q_lower): return get_fact_warning_report()
    if re.search(r'\b(에러|오류|error)\b', q_lower): return get_fact_error_report()
    if re.search(r'\b(개수|몇개|요약|활동|전체|7일)\b', q_lower): return get_fact_activity_summary()
        
    # 🎯 3. 어떤 키워드에도 안 걸리는 후속 대화 ("이건 어때?", "저건?") -> LLM 문맥 추론
    return await call_ollama_with_context(latest_query, history_context, "general")

async def call_ollama_with_context(latest_query: str, history_context: str, target_type: str) -> str:
    db_context = ""
    try:
        with get_db_connection() as conn:
            # 타겟 타입에 맞춘 최신 DB 샘플 추출 (LLM이 참고할 팩트 데이터)
            if target_type == "ide_info":
                rows = conn.execute("SELECT source_tool, raw_message FROM ide_activity_logs WHERE source_tool LIKE '%IDE%' OR raw_message LIKE '%IDE%' LIMIT 20").fetchall()
                db_context = "IDE 로그:\n" + "\n".join([f"- {r[0]}: {r[1][:100]}" for r in rows])
            elif target_type == "warn":
                rows = conn.execute("SELECT raw_message FROM ide_activity_logs WHERE raw_message LIKE '%warn%' LIMIT 10").fetchall()
                db_context = "경고 로그:\n" + "\n".join([f"- {r[0][:150]}" for r in rows])
            elif target_type == "error":
                rows = conn.execute("SELECT raw_message FROM ide_activity_logs WHERE raw_message LIKE '%error%' LIMIT 10").fetchall()
                db_context = "에러 로그:\n" + "\n".join([f"- {r[0][:150]}" for r in rows])
            else:
                rows = conn.execute("SELECT source_tool, raw_message FROM ide_activity_logs ORDER BY rowid DESC LIMIT 5").fetchall()
                db_context = "최근 활동 로그:\n" + "\n".join([f"- {r[0]}: {r[1][:100]}" for r in rows])
                
            if not rows: db_context = "관련 데이터 없음."
    except Exception: db_context = "DB 조회 실패"

    system_prompt = f"""당신은 Logmon AI, 시스템 로그 분석 어시스턴트입니다.
[이전 대화 기록]을 통해 현재 대화의 맥락(사용자가 지칭하는 에러나 경고 등)을 반드시 파악하세요.
[컨텍스트 데이터]가 있다면 참고하고, 최종적으로 오직 [최신 질문]에 대해서만 명확하고 간결하게 답변하세요.

[이전 대화 기록]
{history_context if history_context else "이전 대화 없음."}

[컨텍스트 데이터 (최신 DB 조회결과)]
{db_context}
"""
    
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {"model": MODEL_NAME, "prompt": f"{system_prompt}\n\n최신 질문: {latest_query}", "stream": False, "options": {"temperature": 0.3}}
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(endpoint, json=payload)
            return response.json().get("response", "데이터 분석 완료.")
    except Exception: return "서비스 연결 오류"

def parse_vacuum_clean_query(prompt: str) -> tuple[str, str]:
    """
    프론트엔드에서 넘어온 전체 텍스트에서 '최신 질문'을 분리하고,
    과거 유저-AI 대화 3턴(약 6개 텍스트 블록)을 유지하여 문맥으로 묶어냅니다.
    """
    clean_q = prompt.replace('"', '').replace("'", "")
    
    if re.search(r'user avatar', clean_q, re.IGNORECASE):
        blocks = re.split(r'(?i)user avatar', clean_q)
        latest_raw = blocks[-1]
        latest_query = re.split(r'(?i)assistant avatar', latest_raw)[0].strip()
        history_lines = []
        for block in blocks[:-1]:
            if not block.strip(): continue
            parts = re.split(r'(?i)assistant avatar', block)
            user_text = parts[0].strip()
            if user_text:
                history_lines.append(f"사용자: {user_text}")
            if len(parts) > 1:
                ai_text = parts[1].strip()
                if ai_text:
                    history_lines.append(f"AI: {ai_text}")
        history = "\n\n".join(history_lines[-6:])
        return latest_query, history

    blocks = re.split(r'\[User Query\]|<start_of_turn>user', clean_q)
    latest_query = blocks[-1].replace('<end_of_turn>', '').strip()
    history = "\n".join([b[:200] for b in blocks[-4:-1] if b.strip()])
    return latest_query, history

def get_fact_token_report():
    try:
        with get_db_connection() as conn:
            rows = conn.execute("SELECT raw_message FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-1 days') AND raw_message LIKE '%chat messages%'").fetchall()
            cnt = sum([int(re.search(r'with (\d+) chat messages', r[0]).group(1)) for r in rows if re.search(r'with (\d+) chat messages', r[0])])
            return f"📊 **[AI 인프라]** 최근 24시간 추정 토큰량: `{cnt * 250:,} tokens`임"
    except: return "❌ 토큰 장애"

def get_fact_warning_report():
    try:
        with get_db_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-3 days') AND (raw_message LIKE '%warn%' OR raw_message LIKE '%warning%')").fetchone()[0] or 0
            return f"⚠️ **[최근 3일 경고 정산]** 총 경고 건수: `{cnt}개`임"
    except: return "❌ 경고 장애"

def get_fact_error_report():
    try:
        with get_db_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-7 days') AND (raw_message LIKE '%error%' OR raw_message LIKE '%fail%')").fetchone()[0] or 0
            return f"🚨 **[최근 7일 에러 정산]** 총 에러 건수: `{cnt}개`임"
    except: return "❌ 에러 장애"

def get_fact_activity_summary():
    try:
        with get_db_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-1 days')").fetchone()[0] or 0
            return f"📝 **[오늘 활동 요약]** 최근 24시간 로그: `{total}개`임"
    except: return "❌ 활동 장애"