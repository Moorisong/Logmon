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
    """이전 답변 찌꺼기에 의한 오염을 100% 진공 세척하고 순수 유저 질문만 라우팅하는 엔진"""
    # 🎯 1. 이전 챗봇 답변 잔상을 완벽히 분리수거하여 순수 질문만 징집
    question = parse_vacuum_clean_query(prompt)
    q_lower = question.lower()
    
    logger.info(f"[진공 세척 완료] 이전 답변 차단된 찐 유저 질문: '{question}'")
    
    # 🎯 2. 상호 배타적 정밀 징집 분기 필터링 매트릭스
    
    # [분기 A] 일주일 / 7일 범위 누적 통계 질의
    if "일주일" in q_lower or "7일" in q_lower:
        return get_fact_weekly_total_report()
        
    # [분기 B] SYSTEM / system 특정 흔적 질의
    elif "system" in q_lower or "시스템" in q_lower:
        return get_fact_system_trace_report()
        
    # [분기 C] 에러 / 오류 관련 본문 전수조사 질의
    elif "에러" in q_lower or "오류" in q_lower or "error" in q_lower or "fail" in q_lower:
        return get_fact_error_report()
        
    # [분기 D] 토큰 사용량 / 역산 관련 질의
    elif "토큰" in q_lower or "token" in q_lower or "사용량" in q_lower:
        return get_fact_token_report()
        
    # [분기 E] 경고 로그 관련 질의
    elif "경고" in q_lower or "warn" in q_lower:
        return get_fact_warning_report()
        
    # [분기 F] 오늘 자 전체 개수 및 요약 기본 질의
    elif any(k in q_lower for k in ["개수", "몇개", "몇 개", "요약", "내역", "활동", "전체", "장부"]):
        return get_fact_activity_summary()
        
    # 🔓 일반 개발/코드 프리패스 라인 (장부 관련 질문이 전혀 아닐 때)
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False, "options": {"num_thread": OLLAMA_NUM_THREAD}}
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json().get("response", "")
    except Exception:
        return get_fact_activity_summary()


def parse_vacuum_clean_query(prompt: str) -> str:
    """이전 챗봇 답변이나 시스템 로그 찌꺼기가 남긴 단어 오염을 차단하고, 가장 최신의 순수 유저 텍스트만 리턴함"""
    if "[User Query]" in prompt:
        try:
            # 💡 1단계: 맨 마지막 유저 쿼리 블록 징집
            parts = prompt.split("[User Query]")
            last_part = parts[-1]
            
            # 💡 2단계: 에이전트 턴 종결자 뒤쪽 제거
            clean_q = last_part.split("<end_of_turn>")[0]
            
            # 💡 3단계: 만에 하나 이전 모델 답변(model)이나 시스템 리포트 양식 문구 내용물이 섞여 있다면 원천 박멸
            clean_q = clean_q.split("<start_of_turn>") [0]
            clean_q = re.sub(r'(리포트|정밀|통계|조회|기준|시각|확인됨|가이드|우회|싱크|실측|지표|건수|개수임)', '', clean_q)
            
            return clean_q.strip()
        except Exception: pass
    return prompt


def get_fact_system_trace_report() -> str:
    conn = sqlite3.connect(REAL_DB_PATH)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE date(timestamp) = date('now', 'localtime') AND (source_tool LIKE '%system%' OR raw_message LIKE '%system%');")
        system_cnt = cursor.fetchone()[0] or 0
        response = f"🖥️ **[LogMon 장부 SYSTEM 흔적 정밀 검증 리포트]**\n"
        response += f"- **조회 기준 시각:** `{now_str} (KST)`\n"
        response += f"--- \n"
        response += f"🔥 **오늘 자 장부 본문/툴 기준 SYSTEM 기록 찐 건수:** **`{system_cnt}개`임**\n\n"
        return response
    except Exception as e: return f"❌ SYSTEM 조회 장애: {e}"
    finally: conn.close()


def get_fact_weekly_total_report() -> str:
    conn = sqlite3.connect(REAL_DB_PATH)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE date(timestamp) >= date('now', 'localtime', '-6 days');")
        weekly_cnt = cursor.fetchone()[0] or 0
        response = f"📅 **[LogMon 장부 최근 7일 전체 누적 통계]**\n"
        response += f"- **조회 기준 시각:** `{now_str} (KST)`\n"
        response += f"--- \n"
        response += f"🔥 **최근 일주일(7일간) 동안 장부에 적재된 총 로그 누적량:** **`{weekly_cnt}개`임 확인되었습니다.**\n\n"
        return response
    except Exception as e: return f"❌ 일주일 조회 장애: {e}"
    finally: conn.close()


def get_fact_error_report() -> str:
    conn = sqlite3.connect(REAL_DB_PATH)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE date(timestamp) = date('now', 'localtime') AND (raw_message LIKE '%error%' OR raw_message LIKE '%fail%')")
        today_err_cnt = cursor.fetchone()[0] or 0
        response = f"🚨 **[LogMon 장부 실시간 정방향 정산 리포트]**\n"
        response += f"- **조회 기준 시각:** `{now_str} (KST)`\n"
        response += f"--- \n"
        response += f"🔥 **오늘 자 본문 텍스트 전수조사 찐 에러 건수:** **`{today_err_cnt}개`임**\n\n"
        return response
    except Exception as e: return f"❌ 에러 조회 장애: {e}"
    finally: conn.close()


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
        return response
    except Exception as e: return f"❌ 토큰 조회 장애: {e}"
    finally: conn.close()


def get_fact_warning_report() -> str:
    conn = sqlite3.connect(REAL_DB_PATH)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE date(timestamp) >= date('now', 'localtime', '-2 days') AND (event_type LIKE '%WARN%' OR raw_message LIKE '%warn%')")
        warn_cnt = cursor.fetchone()[0] or 0
        response = f"⚠️ **[LogMon 장부 경고 통계 리포트]**\n"
        response += f"- **조회 기준 시각:** `{now_str} (KST)`\n"
        response += f"--- \n"
        response += f"🔥 **최근 3일 동안 발생한 총 경고 로그 개수:** **`{warn_cnt}개`임 확인되었습니다.**"
        return response
    except Exception as e: return f"❌ 경고 조회 장애: {e}"
    finally: conn.close()


def get_fact_activity_summary() -> str:
    conn = sqlite3.connect(REAL_DB_PATH)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE date(timestamp) = date('now', 'localtime') AND task_name != 'STATISTICS'")
        today_total_logs = cursor.fetchone()[0] or 0
        cursor.execute("SELECT source_tool, timestamp, event_type, raw_message FROM ide_activity_logs WHERE date(timestamp) = date('now', 'localtime') AND task_name != 'STATISTICS' ORDER BY timestamp DESC LIMIT 5")
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
    except Exception as e: return f"❌ 활동 조회 장애: {e}"
    finally: conn.close()