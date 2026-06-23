import sqlite3
import logging
from typing import Dict, Any, Optional
import re

from backend.db.connection import get_connection

logger = logging.getLogger(__name__)

# =====================================================================
# 🚨 [추가됨] DB 초기화(테이블 자동 생성) 로직
# =====================================================================
def init_db():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ide_activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_key TEXT NOT NULL,
                source_tool TEXT,
                timestamp TEXT NOT NULL,
                event_type TEXT,
                task_name TEXT,
                duration_seconds REAL DEFAULT 0,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                raw_message TEXT,
                has_code_block INTEGER DEFAULT 0
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_time ON ide_activity_logs(user_key, timestamp);")
        conn.commit()
        logger.info("✅ DB 초기화: ide_activity_logs 테이블 준비 완료")
    except sqlite3.Error as e:
        logger.error(f"❌ DB 초기화 에러: {e}")
    finally:
        conn.close()
# =====================================================================

def check_duplicate_log(user_key: str, timestamp: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM ide_activity_logs WHERE user_key = ? AND timestamp = ? LIMIT 1;",
            (user_key, timestamp)
        )
        return bool(cursor.fetchone())
    finally:
        conn.close()

def insert_activity_log(data: Dict[str, Any]) -> Optional[int]:
    user_key = data.get("user_key")
    timestamp = data.get("timestamp")
    event_type = data.get("event_type") or "INFO"
    raw_msg = str(data.get("raw_message") or "")
    raw_lower = raw_msg.lower()

    # =====================================================================
    # 🚨 [핵심 3대 지표 필터링 (Auto-Discovery)]
    # =====================================================================
    task_name = ""

    if "loadcodeassist" in raw_lower or "fetchavailablemodels" in raw_lower or "cloudcode" in raw_lower or "generate" in raw_lower:
        task_name = "ai_assisted"
    elif "error" in raw_lower or "exception" in raw_lower or "fail" in raw_lower or "traceback" in raw_lower:
        task_name = "debugging"
        event_type = "ERROR" 
    elif re.search(r"(\.py|\.tsx?|\.jsx?|\.go|\.java|\.cpp|\.html|\.css)", raw_lower) or "save" in raw_lower:
        task_name = "workspace_active"
    else:
        logger.debug(f"🚫 [필터링 됨] 3대 지표와 무관한 로그 폐기 (미저장)")
        return None
    # =====================================================================

    data["task_name"] = task_name
    enriched_message = f"[ACTION: {task_name}] {raw_msg}"

    conn = get_connection()
    try:
        if check_duplicate_log(user_key, timestamp): 
            return None

        insert_query = """
            INSERT INTO ide_activity_logs (
                user_key, source_tool, timestamp, event_type, 
                task_name, duration_seconds, input_tokens, output_tokens, 
                raw_message, has_code_block
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        params = (
            user_key, data.get("source_tool", "UNKNOWN_TOOL"), timestamp,
            event_type, task_name, data.get("duration_seconds", 0),
            data.get("input_tokens", 0), data.get("output_tokens", 0),
            enriched_message, data.get("has_code_block", 0)
        )
        
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute(insert_query, params)
        last_row_id = cursor.lastrowid
        
        # LLM 추론 고도화: 구조화 템플릿 적용
        from backend.llm.utils import format_log_message
        structured_message = format_log_message(
            log_id=last_row_id, timestamp=timestamp,
            source=data.get("source_tool", "UNKNOWN_TOOL"),
            log_level=event_type, target=task_name,
            raw_message=enriched_message
        )
        cursor.execute(
            "UPDATE ide_activity_logs SET raw_message = ? WHERE id = ?;",
            (structured_message, last_row_id)
        )
        data["raw_message"] = structured_message
        
        cursor.execute("COMMIT;")
        logger.info(f"✅ 핵심 로그 적재 완료 [ID: {last_row_id}, Task: {task_name}]")
        return last_row_id
        
    except sqlite3.Error as e:
        logger.error(f"로그 삽입 에러: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def cleanup_ttl_logs() -> list[int]:
    conn = get_connection()
    deleted_ids = []
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("SELECT id FROM ide_activity_logs WHERE timestamp < datetime('now', '-7 days', 'localtime')")
        rows = cursor.fetchall()
        deleted_ids = [r[0] for r in rows]
        if deleted_ids:
            placeholders = ",".join(["?"] * len(deleted_ids))
            cursor.execute(f"DELETE FROM ide_activity_logs WHERE id IN ({placeholders})", deleted_ids)
        cursor.execute("COMMIT;")
    finally:
        conn.close()
    return deleted_ids

def cleanup_old_logs(limit: int = 100) -> list[int]:
    conn = get_connection()
    deleted_ids = []
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("SELECT id FROM ide_activity_logs ORDER BY timestamp ASC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        deleted_ids = [r[0] for r in rows]
        if deleted_ids:
            placeholders = ",".join(["?"] * len(deleted_ids))
            cursor.execute(f"DELETE FROM ide_activity_logs WHERE id IN ({placeholders})", deleted_ids)
        cursor.execute("COMMIT;")
    finally:
        conn.close()
    return deleted_ids

def delete_all_logs_by_user(user_key: str) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ide_activity_logs WHERE user_key = ?", (user_key,))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count
    finally:
        conn.close()

def vacuum_db() -> None:
    conn = get_connection()
    try:
        conn.isolation_level = None
        cursor = conn.cursor()
        cursor.execute("VACUUM;")
    finally:
        conn.close()