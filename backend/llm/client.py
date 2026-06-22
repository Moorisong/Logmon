import os
import logging
import re
from datetime import datetime
import sqlite3

logger = logging.getLogger(__name__)

REAL_DB_PATH = "/app/data/logmon.db"

async def generate_completion(prompt: str) -> str:
    """Ollama API 전송 전 패킷을 100% 완벽하게 통제하는 다이렉트 무결성 엔진"""
    context, question = parse_prompt(prompt)
    
    target_q = question if question else prompt
    q_lower = target_q.lower()
    
    logger.info(f"[최종 밸런스 가로채기] 분석 질문: {target_q[:50]}")
    
    # 💥 [순서 역전] 전체 개수, 요약, 내역, 활동 의도가 보이면 에러 단어가 섞여있어도 이리로 먼저 인터셉트!
    if any(k in q_lower for k in ["개수", "몇개", "몇 개", "요약", "내역", "활동", "장부", "전체"]):
        return get_real_activity_summary()
        
    # [2순위 인터셉트] 순수 에러 및 오류 질의
    elif any(k in q_lower for k in ["에러", "오류", "error", "fail", "발생"]):
        return get_real_error_report()
        
    return get_real_activity_summary()


def parse_prompt(prompt: str) -> tuple:
    context, question = "", ""
    if "[과거 로그 컨텍스트]" in prompt and "[사용자 질문]" in prompt:
        try:
            parts = prompt.split("[과거 로그 컨텍스트]")
            if len(parts) > 1:
                subparts = parts[1].split("[사용자 질문]")
                if len(subparts) > 1:
                    context = subparts[0].strip()
                    question = subparts[1].split("[답변]")[0].strip()
        except Exception: pass
    return context, question


def get_real_error_report() -> str:
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
        
        response = f"🚨 **[LogMon 신규 장부 정방향 정산 리포트]**\n"
        response += f"- **조회 실시간 시각:** `{now_str} (KST)`\n"
        response += f"--- \n"
        response += f"🔥 **오늘 자 본문 텍스트 전수조사 찐 에러 건수:** **`{today_err_cnt}개`임**\n\n"
        response += f"*가이드: event_type 컬럼 사기극을 우회하여 본문 내 error/fail 흔적을 완벽하게 색출해 낸 무결성 지표입니다.*"
        return response
    except Exception as e:
        return f"❌ 에러 장부 조회 장애 발생: {e}"
    finally:
        conn.close()


def get_real_activity_summary() -> str:
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
        
        if not rows:
            response += "- 오늘 기록된 최신 활동 로그가 존재하지 않습니다."
        for r in rows:
            msg_summary = (r[3] or "").strip().replace('\n', ' ')[:65]
            response += f"- `[{r[1]}]` **{r[0]}** ({r[2]}) ➡️ `{msg_summary}...`\n"
        return response
    except Exception as e:
        return f"❌ 활동 장부 조회 장애 발생: {e}"
    finally:
        conn.close()