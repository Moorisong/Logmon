import sqlite3
import logging
from typing import Dict, Any, Optional, List
import re
from backend.db.connection import get_connection

logger = logging.getLogger(__name__)

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
                has_code_block INTEGER DEFAULT 0,
                file_path TEXT DEFAULT 'UNKNOWN',
                workspace_active INTEGER DEFAULT 0
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_time ON ide_activity_logs(user_key, timestamp);")
        conn.commit()
        logger.info("✅ DB 초기화: ide_activity_logs 테이블 준비 완료")
    except sqlite3.Error as e:
        logger.error(f"❌ DB 초기화 에러: {e}")
    finally:
        conn.close()

def check_duplicate_log(user_key: str, timestamp: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM ide_activity_logs WHERE user_key = ? AND timestamp = ? LIMIT 1;", (user_key, timestamp))
        return bool(cursor.fetchone())
    finally:
        conn.close()

def insert_activity_log(data: Dict[str, Any]) -> Optional[int]:
    user_key = data.get("user_key")
    timestamp = data.get("timestamp")
    event_type = data.get("event_type") or "INFO"
    raw_msg = str(data.get("raw_message") or "")
    raw_lower = raw_msg.lower()

    # 3대 지표 필터링
    task_name = ""
    if any(k in raw_lower for k in ["loadcodeassist", "fetchavailablemodels", "cloudcode", "generate"]):
        task_name = "ai_assisted"
    elif any(k in raw_lower for k in ["error", "exception", "fail", "traceback"]):
        task_name = "debugging"
        event_type = "ERROR" 
    elif re.search(r"(\.py|\.tsx?|\.jsx?|\.go|\.java|\.cpp|\.html|\.css)", raw_lower) or "save" in raw_lower:
        task_name = "workspace_active"
    else:
        return None

    # 작업 활성 상태 및 파일 경로 처리
    is_workspace_active = 1 if task_name == "workspace_active" else 0
    file_path = data.get("file_path") or "UNKNOWN"

    # 토큰값 보강
    in_tok = data.get("input_tokens", 0) or 0
    out_tok = data.get("output_tokens", 0) or 0
    if in_tok == 0 and out_tok == 0:
        match = re.search(r"tokens[:\s]*(\d+)", raw_msg, re.IGNORECASE)
        if match: in_tok = int(match.group(1))

    data["task_name"] = task_name
    enriched_message = f"[ACTION: {task_name}] {raw_msg}"

    conn = get_connection()
    try:
        if check_duplicate_log(user_key, timestamp): return None

        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")
        
        insert_query = """
            INSERT INTO ide_activity_logs (
                user_key, source_tool, timestamp, event_type, 
                task_name, duration_seconds, input_tokens, output_tokens, 
                raw_message, has_code_block, file_path, workspace_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(insert_query, (
            user_key, data.get("source_tool", "UNKNOWN_TOOL"), timestamp,
            event_type, task_name, data.get("duration_seconds", 0.0),
            in_tok, out_tok, enriched_message, data.get("has_code_block", 0),
            file_path, is_workspace_active
        ))
        last_row_id = cursor.lastrowid
        
        from backend.llm.utils import format_log_message
        structured_message = format_log_message(last_row_id, timestamp, data.get("source_tool", "UNKNOWN_TOOL"), event_type, task_name, enriched_message)
        
        cursor.execute("UPDATE ide_activity_logs SET raw_message = ? WHERE id = ?;", (structured_message, last_row_id))
        cursor.execute("COMMIT;")
        logger.info(f"✅ 핵심 로그 적재 완료 [ID: {last_row_id}, Task: {task_name}, Path: {file_path}]")
        return last_row_id
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"로그 삽입 에러: {e}")
        raise
    finally:
        conn.close()

def cleanup_ttl_logs(days: int = 7) -> List[int]:
    conn = get_connection()
    deleted_ids = []
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute(f"SELECT id FROM ide_activity_logs WHERE timestamp < datetime('now', '-{days} days', 'localtime')")
        rows = cursor.fetchall()
        deleted_ids = [r[0] for r in rows]
        if deleted_ids:
            placeholders = ",".join(["?"] * len(deleted_ids))
            cursor.execute(f"DELETE FROM ide_activity_logs WHERE id IN ({placeholders})", deleted_ids)
        cursor.execute("COMMIT;")
    finally:
        conn.close()
    return deleted_ids

def cleanup_old_logs(limit: int = 100) -> List[int]:
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

def delete_unknown_logs() -> int:
    """시스템 업데이트 이전의 'UNKNOWN' 로그를 삭제하여 분석 품질을 높입니다."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ide_activity_logs WHERE file_path = 'UNKNOWN'")
        deleted_count = cursor.rowcount
        conn.commit()
        logger.info(f"🧹 정제 완료: {deleted_count}개의 'UNKNOWN' 로그 삭제됨.")
        return deleted_count
    finally:
        conn.close()

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