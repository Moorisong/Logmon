import sqlite3
import logging
from typing import Dict, Any, Optional

from backend.db.connection import get_connection

logger = logging.getLogger(__name__)

def check_duplicate_log(user_key: str, timestamp: str) -> bool:
    """
    멱등성 보장을 위해 동일한 user_key와 timestamp를 가진 로그가 존재하는지 확인합니다.
    존재하면 True, 없으면 False를 반환합니다.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM ide_activity_logs WHERE user_key = ? AND timestamp = ? LIMIT 1;",
            (user_key, timestamp)
        )
        result = cursor.fetchone()
        return bool(result)
    except sqlite3.Error as e:
        logger.error(f"중복 확인 중 에러 발생: {e}")
        return False
    finally:
        conn.close()

def insert_activity_log(data: Dict[str, Any]) -> Optional[int]:
    """
    바인딩 쿼리(?)를 사용하여 SQL Injection을 방어하며 활동 로그를 삽입합니다.
    반환값은 삽입된 레코드의 id (정수) 입니다.
    """
    user_key = data.get("user_key")
    timestamp = data.get("timestamp")
    
    if check_duplicate_log(user_key, timestamp):
        logger.info(f"중복된 로그 삽입 스킵: {user_key} at {timestamp}")
        return None

    insert_query = """
        INSERT INTO ide_activity_logs (
            user_key, source_tool, timestamp, event_type, 
            task_name, duration_seconds, input_tokens, output_tokens, 
            raw_message, has_code_block
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    params = (
        user_key,
        data.get("source_tool", "UNKNOWN_TOOL"),
        timestamp,
        data.get("event_type", "UNKNOWN_EVENT"),
        data.get("task_name", "UNKNOWN"),
        data.get("duration_seconds", 0),
        data.get("input_tokens", 0),
        data.get("output_tokens", 0),
        data.get("raw_message"),
        data.get("has_code_block", 0)
    )
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")
        
        cursor.execute(insert_query, params)
        last_row_id = cursor.lastrowid
        
        cursor.execute("COMMIT;")
        logger.info(f"로그 삽입 성공. ID: {last_row_id}")
        return last_row_id
        
    except sqlite3.Error as e:
        logger.error(f"로그 삽입 중 에러 발생: {e}")
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
        if deleted_ids:
            logger.info(f"SQLite 7일 TTL 클리닝 완료. 삭제된 레코드 수: {len(deleted_ids)}")
    except sqlite3.Error as e:
        logger.error(f"SQLite TTL 클리닝 중 에러: {e}")
        conn.rollback()
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
        if deleted_ids:
            logger.info(f"SQLite FIFO 클리닝 완료. 삭제된 레코드 수: {len(deleted_ids)}")
    except sqlite3.Error as e:
        logger.error(f"SQLite FIFO 클리닝 중 에러: {e}")
        conn.rollback()
    finally:
        conn.close()
        
    return deleted_ids

def delete_all_logs_by_user(user_key: str) -> int:
    """
    특정 API Key 소유자의 모든 수집 활동 로그 레코드를 SQLite에서 일괄 물리 격리 삭제 처리합니다.
    """
    conn = get_connection()
    deleted_count = 0
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")
        
        cursor.execute("DELETE FROM ide_activity_logs WHERE user_key = ?", (user_key,))
        deleted_count = cursor.rowcount
        
        cursor.execute("COMMIT;")
        logger.info(f"⚙️ SQLite 클리닝 완료. 유저 [{user_key}] 레코드 완전 파쇄 완료. (건수: {deleted_count})")
        return deleted_count
    except sqlite3.Error as e:
        logger.error(f"SQLite 유저 데이터 파쇄 프로세싱 예외 발생: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def vacuum_db() -> None:
    """
    DELETE 수행 후 실제 디스크상의 빈 공간을 환수하기 위해 VACUUM 명령을 실행합니다.
    """
    conn = get_connection()
    try:
        # SQLite의 VACUUM은 트랜잭션 밖에서 실행해야 하므로 isolation_level을 None으로 설정합니다.
        conn.isolation_level = None
        cursor = conn.cursor()
        cursor.execute("VACUUM;")
        logger.info("SQLite VACUUM 실행 완료 - 디스크 공간 최적화 완료")
    except sqlite3.Error as e:
        logger.error(f"SQLite VACUUM 실행 중 에러 발생: {e}")
    finally:
        conn.close()

