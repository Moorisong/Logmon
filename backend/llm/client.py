import os
import httpx
import logging
import re
from datetime import datetime
import sqlite3

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://logmon-ollama:11434")
try:
    OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "3"))
except ValueError:
    OLLAMA_NUM_THREAD = 3

MODEL_NAME = "gemma2:2b"
REAL_DB_PATH = "/app/data/logmon.db"

def get_db_connection():
    return sqlite3.connect(f"file:{REAL_DB_PATH}?mode=ro", uri=True, timeout=30.0)

async def generate_completion(prompt: str) -> str:
    # 🎯 1. 프롬프트에서 '최신 질문'과 '과거 대화'를 분리 추출
    latest_query, history_context = parse_vacuum_clean_query(prompt)
    q_lower = latest_query.lower()
    
    logger.info(f"[최신 질의 추출] '{latest_query}' / [히스토리 길이] {len(history_context)}자")
    
    # 🎯 2. 사용자 질문 의도(Intent) 분석 (오직 최신 질의만 검사)
    is_analysis_req = re.search(r'(상세|정리|종류|내용|어떤|무엇|이유|왜|분석|목록|패턴|알려줘|어때)', q_lower)
    
    # 🎯 3. 타겟 엔티티(Entity) 확인
    has_token = re.search(r'(토큰|token|사용량|인프라)', q_lower)
    has_warn = re.search(r'(경고|warn|warning)', q_lower)
    has_error = re.search(r'(에러|오류|error|fail)', q_lower)
    has_system = re.search(r'(system|시스템)', q_lower)
    has_summary = re.search(r'(개수|몇개|몇 개|요약|내역|활동|전체|장부|7일|일주일)', q_lower)
    
    # 🚀 4. 라우팅 분기 (최신 질문 기준)
    if is_analysis_req or (not has_token and not has_warn and not has_error and not has_system and not has_summary):
        # [분기 A] 상세 분석을 요구하거나, 아무 키워드도 없는 일반 대화 -> LLM 추론
        target_type = "general"
        if has_warn: target_type = "warn"
        elif has_error: target_type = "error"
        elif has_system: target_type = "system"
        return await call_ollama_with_context(latest_query, history_context, target_type)
        
    else:
        # [분기 B] 단순 통계/개수를 요구하는 경우 -> 빠르고 정확한 DB SQL 카운트 리턴
        if has_token: return get_fact_token_report()
        elif has_error: return get_fact_error_report()
        elif has_warn: return get_fact_warning_report()
        elif has_system: return get_fact_system_trace_report()
        elif has_summary: return get_fact_activity_summary()
        
    # 안전망 폴백
    return await call_ollama_with_context(latest_query, history_context, "general")


async def call_ollama_with_context(latest_query: str, history_context: str, target_type: str) -> str:
    """DB 데이터와 과거 대화 기록(단기 기억)을 모두 LLM에 주입하는 추론 엔진"""
    db_context = ""
    
    try:
        with get_db_connection() as conn:
            if target_type == "warn":
                rows = conn.execute("SELECT raw_message FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-3 days') AND (raw_message LIKE '%warn%' OR raw_message LIKE '%warning%') LIMIT 10").fetchall()
                db_context = "최근 경고 로그 샘플:\n" + "\n".join([f"- {r[0][:150]}" for r in rows if r[0]])
            elif target_type == "error":
                rows = conn.execute("SELECT raw_message FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-7 days') AND (raw_message LIKE '%error%' OR raw_message LIKE '%fail%') LIMIT 10").fetchall()
                db_context = "최근 에러 로그 샘플:\n" + "\n".join([f"- {r[0][:150]}" for r in rows if r[0]])
            elif target_type == "system":
                rows = conn.execute("SELECT raw_message FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-1 days') AND source_tool LIKE '%system%' LIMIT 10").fetchall()
                db_context = "시스템 로그 샘플:\n" + "\n".join([f"- {r[0][:150]}" for r in rows if r[0]])
            else:
                rows = conn.execute("SELECT event_type, raw_message FROM ide_activity_logs ORDER BY rowid DESC LIMIT 5").fetchall()
                db_context = "최근 전체 활동 로그 샘플:\n" + "\n".join([f"- [{r[0]}] {r[1][:150]}" for r in rows if r[1]])
                
            if len(db_context) < 20:
                db_context = "해당 조건에 맞는 로그 데이터가 DB에 존재하지 않습니다."
    except Exception as e:
        logger.error(f"Context fetching failed: {e}")
        db_context = "데이터베이스 조회 중 오류가 발생했습니다."

    # LLM 앵무새 방지 및 기억력 주입 시스템 프롬프트
    system_prompt = f"""당신은 Logmon AI, 개발자를 돕는 전문 시스템 로그 분석가입니다.
[행동 규칙]
1. [최근 대화 기록]을 참고하여, 사용자가 이전에 했던 질문이나 당신이 직전에 했던 답변을 파악하세요.
2. 직전에 했던 답변을 토씨 하나 틀리지 않고 앵무새처럼 똑같이 반복하는 것을 절대 금지합니다.
3. [로그 데이터 컨텍스트]를 분석하여 사용자의 '최신 질문'에 가장 정확하게 답변하세요.
4. 인사말은 생략하고, 팩트 기반으로 간결하고 가독성 좋게(마크다운 활용) 답변하세요.

[최근 대화 기록 (단기 기억)]
{history_context if history_context else "이전 대화 없음."}

[로그 데이터 컨텍스트]
{db_context}
"""
    
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {
        "model": MODEL_NAME, 
        "prompt": f"{system_prompt}\n\n최신 질문: {latest_query}", 
        "stream": False, 
        # temperature를 0.5로 설정하여 약간의 유연성을 주어 똑같은 대답을 피하도록 유도
        "options": {"num_thread": OLLAMA_NUM_THREAD, "temperature": 0.5} 
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(endpoint, json=payload)
            return response.json().get("response", "데이터 분석 완료.")
    except Exception: return "서비스 연결 오류 발생"


def parse_vacuum_clean_query(prompt: str) -> tuple[str, str]:
    """
    전체 프롬프트 덩어리에서 '가장 최신 질문'과 '과거 대화 2~3턴(History)'을 엄격하게 분리합니다.
    """
    clean_q = prompt.replace('"', '').replace("'", "")
    
    # 1. 태그 기반 파싱 (Gemma 스타일이나 명시적 태그가 있을 경우)
    if "start_of_turn" in clean_q or "User Query" in clean_q:
        blocks = re.split(r'\[User Query\]|<start_of_turn>user|<start_of_turn>model', clean_q)
        blocks = [b.replace('<end_of_turn>', '').strip() for b in blocks if b.strip()]
        
        latest_query = blocks[-1] if blocks else clean_q
        # 최근 2~3개의 턴만 히스토리로 추출
        history_blocks = blocks[-4:-1] if len(blocks) > 1 else []
        history = "\n".join([f"- 이전 대화 내역: {b[:100]}..." for b in history_blocks])
        return latest_query, history
        
    # 2. 일반 텍스트 라인 기반 파싱 (태그가 없을 때 방어 로직)
    lines = [line.strip() for line in clean_q.split('\n') if line.strip()]
    if not lines:
        return clean_q.strip(), ""
        
    latest_query = lines[-1]
    history = "\n".join([f"- 이전 대화 내역: {l[:100]}..." for l in lines[-4:-1]])
    return latest_query, history

# =========================================================================
# 아래는 단순 통계(Metric) 전용 함수들입니다. (유지)
# =========================================================================

def get_fact_token_report() -> str:
    try:
        with get_db_connection() as conn:
            rows = conn.execute("SELECT raw_message FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-1 days') AND raw_message LIKE '%chat messages%'").fetchall()
            cnt = sum([int(re.search(r'with (\d+) chat messages', r[0]).group(1)) for r in rows if re.search(r'with (\d+) chat messages', r[0])])
            return f"📊 **[AI 인프라]** 최근 24시간 추정 토큰량: `{cnt * 250:,} tokens`임"
    except Exception as e: return f"❌ 토큰 장애: {e}"

def get_fact_warning_report() -> str:
    try:
        with get_db_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-3 days') AND (raw_message LIKE '%warn%' OR raw_message LIKE '%warning%')").fetchone()[0] or 0
            return f"⚠️ **[최근 3일 경고 정산]** 총 경고 건수: `{cnt}개`임"
    except Exception as e: return f"❌ 경고 장애: {e}"

def get_fact_error_report() -> str:
    try:
        with get_db_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-7 days') AND (raw_message LIKE '%error%' OR raw_message LIKE '%fail%')").fetchone()[0] or 0
            return f"🚨 **[최근 7일 에러 정산]** 총 에러 건수: `{cnt}개`임"
    except Exception as e: return f"❌ 에러 장애: {e}"

def get_fact_system_trace_report() -> str:
    try:
        with get_db_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-1 days') AND (source_tool LIKE '%system%' OR raw_message LIKE '%system%');").fetchone()[0] or 0
            return f"🖥️ **[SYSTEM 리포트]** 최근 24시간 기록: `{cnt}개`임"
    except Exception as e: return f"❌ SYSTEM 장애: {e}"

def get_fact_activity_summary() -> str:
    try:
        with get_db_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE timestamp >= date('now', 'localtime', '-1 days')").fetchone()[0] or 0
            rows = conn.execute("SELECT source_tool, raw_message FROM ide_activity_logs ORDER BY rowid DESC LIMIT 3").fetchall()
            res = f"📝 **[오늘 활동 요약]** 최근 24시간 로그: `{total}개`임\n"
            for r in rows:
                res += f"- **{r[0]}** ➡️ `{(r[1] or '').strip()[:30]}...`\n"
            return res
    except Exception as e: return f"❌ 활동 장애: {e}"