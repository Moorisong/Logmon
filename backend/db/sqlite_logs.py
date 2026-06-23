import sqlite3
import logging
from typing import Dict, Any, Optional
import re

from backend.db.connection import get_connection

logger = logging.getLogger(__name__)

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
    logger.info(f"🚨 [수신된 원본 데이터] IDE 에이전트 페이로드: {data}")

    user_key = data.get("user_key")
    timestamp = data.get("timestamp")
    
    task_name = str(data.get("task_name") or "UNKNOWN_TASK").strip()
    event_type = data.get("event_type") or "INFO"
    raw_msg = str(data.get("raw_message") or "")
    
    # --- [Auto-Discovery 강화] 터미널 명령어 완전 추적 ---
    if task_name.upper() in ["UNKNOWN_TASK", "UNKNOWN", "NONE", "NULL", ""]:
        raw_lower = raw_msg.lower()
        
        # 정규식을 통해 [Terminal] Command completed: 뒷부분을 강제로 추출
        terminal_match = re.search(r"\[terminal\] command completed:\s*(git\s+[a-z]+)", raw_lower)
        
        if terminal_match:
            # 예: "git commit", "git push" 등 정확한 명령어만 추출
            task_name = terminal_match.group(1).strip()
        elif "git commit" in raw_lower:
            task_name = "git commit"
        elif "git push" in raw_lower:
            task_name = "git push"
        elif "git pull" in raw_lower:
            task_name = "git pull"
        elif "error" in raw_lower or "exception" in raw_lower:
            task_name = "error_log"
            
    data["task_name"] = task_name
    enriched_message = f"[ACTION: {task_name}] {raw_msg}"

    conn = get_connection()
    try:
        if check_duplicate_log(user_key, timestamp): return None

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
        
        if task_name != "STATISTICS":
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
        logger.info(f"로그 구조화 적재 완료 [ID: {last_row_id}, Task: {task_name}]")
        return last_row_id
        
    except sqlite3.Error as e:
        logger.error(f"로그 삽입 에러: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

# ... [나머지 cleanup, vacuum 로직 동일] ...
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
        if deleted_ids: vacuum_db()
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
        if deleted_ids: vacuum_db()
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