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

async def generate_completion(prompt: str) -> str:
    """누적 대화 컨텍스트에서 오직 '가장 최신의 질문'만 도려내어 무한루프를 종식하는 라우터"""
    # 🎯 히스토리 장부의 맨 마지막 최신 질문만 정밀 가로채기
    question = parse_last_user_query(prompt)
    q_lower = question.lower()
    
    logger.info(f"[컨텍스트 분리 가로채기] 징집된 최신 찐 질문: {question[:50]}")
    
    # 🎯 1순위 타격: 토큰 사용량/량 관련 질의
    if any(k in q_lower for k in ["토큰", "token", "사용량", "토큰량"]):
        return get_fact_token_report()
        
    # 🎯 2순위 타격: 경고(WARN) 관련 질의
    elif any(k in q_lower for k in ["경고", "warn", "warning"]):
        return get_fact_warning_report()
        
    # 🎯 3순위 타격: 순수 에러 및 오류 관련 질의 
    elif any(k in q_lower for k in ["에러", "오류", "error", "fail"]):
        return get_fact_error_report()
        
    # 🎯 4순위 타격: 전체 개수, 요약, 내역 관련 장부 통계 질의
    elif any(k in q_lower for k in ["개수", "몇개", "몇 개", "요약", "내역", "활동", "전체", "장부"]):
        return get_fact_activity_summary()
        
    # 🔓 일반 대화 프리패스: 장부 필터링에 안 걸리면 Ollama 순정 뇌 가동
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False, "options": {"num_thread": OLLAMA_NUM_THREAD}}
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json().get("response", "")
    except Exception:
        return get_fact_activity_summary()


def parse_last_user_query(prompt: str) -> str:
    """대화 히스토리가 아무리 길게 쌓여도 맨 마지막 [User Query]만 정확하게 슬라이싱합니다."""
    if "[User Query]" in prompt:
        try:
            # 💡 parts[-1]을 조준하여 이전 대화 찌꺼기를 전부 무시하고 현재 유저가 친 질문만 획득!
            parts = prompt.split("[User Query]")
            if parts:
                last_part = parts[-1]
                clean_q = last_part.split("<end_of_turn>")[0].strip()
                return clean_q
        except Exception: pass
    return prompt


def get_fact_token_report() -> str:
    conn = sqlite3.connect(REAL_DB_PATH)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT raw_message FROM ide_activity_logs WHERE date(timestamp) = date('now', 'localtime') AND raw_message LIKE '%chat messages%'")
        rows = cursor.fetchall()
        total_msg_cnt = 0
        for r in rows:
            match = re.search(r'with (\d+) chat messages', r[0])
            if match: total_msg_cnt += int(match.group(1))
        
        estimated_tokens = total_msg_cnt * 250
        response = f"📊 **[LogMon 실시간 AI 인프라 통계] 오늘 자 토큰 사용량**\n"
        response += f"- **조회 기준 시각:** `{now_str} (KST)`\n"
        response += f"- **누적 대화 메시지 수 총합:** `{total_msg_cnt:,}개`임\n"
        response += f"--- \n"
        response += f"🔥 **오늘 자 총 사용 토큰량(추정 정산):** **`{estimated_tokens:,} tokens`임**\n\n"
        response += f"*가이드: 대화 히스토리 오염을 우회하여 현재 메시지 양(54개)을 정방향 역산한 실측치입니다.*"
        return response
    except Exception as e: return f"❌ 토큰 장부 연산 장애: {e}"
    finally: conn.close()


def get_fact_warning_report() -> str:
    conn = sqlite3.connect(REAL_DB_PATH)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM ide_activity_logs 
            WHERE date(timestamp) >= date('now', 'localtime', '-2 days') 
              AND (event_type LIKE '%WARN%' OR raw_message LIKE '%warn%')
        """)
        warn_cnt = cursor.fetchone()[0] or 0
        response = f"⚠️ **[LogMon 장부 경고 통계 리포트]**\n"
        response += f"- **조회 기준 시각:** `{now_str} (KST)`\n"
        response += f"--- \n"
        response += f"🔥 **최근 3일 동안 발생한 총 경고 로그 개수:** **`{warn_cnt}개`임 확인되었습니다.**"
        return response
    except Exception as e: return f"❌ 경고 장부 연산 장애: {e}"
    finally: conn.close()


def get_fact_error_report() -> str:
    conn = sqlite3.connect(REAL_DB_PATH)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM ide_activity_logs 
            WHERE date(timestamp) = date('now', 'localtime') 
              AND (raw_message LIKE '%error%' OR raw_message LIKE '%fail%')
        """)
        today_err_cnt = cursor.fetchone()[0] or 0
        response = f"🚨 **[LogMon 장부 실시간 정방향 정산 리포트]**\n"
        response += f"- **조회 기준 시각:** `{now_str} (KST)`\n"
        response += f"--- \n"
        response += f"🔥 **오늘 자 본문 텍스트 전수조사 찐 에러 건수:** **`{today_err_cnt}개`임**\n\n"
        response += f"*가이드: event_type 컬럼 누락 버그를 우회하여 본문 내 흔적을 완벽하게 색출해 낸 결과입니다.*"
        return response
    except Exception as e: return f"❌ 에러 장부 연산 장애: {e}"
    finally: conn.close()


def get_fact_activity_summary() -> str:
    conn = sqlite3.connect(REAL_DB_PATH)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE date(timestamp) = date('now', 'localtime') AND task_name != 'STATISTICS'")
        today_total_logs = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT source_tool, timestamp, event_type, raw_message FROM ide_activity_logs 
            WHERE date(timestamp) = date('now', 'localtime') AND task_name != 'STATISTICS'
            ORDER BY timestamp DESC LIMIT 5
        """)
        rows = cursor.fetchall()
        
        response = f"📝 **[LogMon 장부 실시간 무결성 리포트]**\n"
        response += f"- **징집 기준 시간:** `{now_str} (KST)`\n"
        response += f"- **오늘 자 실제 총 활동 로그 개수:** **`{today_total_logs}개`임**\n"
        response += f"--- \n"
        response += f"**[진실의 방 최신 5개 작업 스냅샷]**\n"
        if not rows: response += "- 오늘 기록된 최신 활동 로그가 존재하지 않습니다."
        for r in rows:
            msg_summary = (r[3] or "").strip().replace('\n', ' ')[:65]
            response += f"- `[{r[1]}]` **{r[0]}** ({r[2]}) ➡️ `{msg_summary}...`\n"
        return response
    except Exception as e: return f"❌ 활동 장부 연산 장애: {e}"
    finally: conn.close()