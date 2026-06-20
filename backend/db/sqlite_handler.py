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
        # 안전한 폴백: 에러 시 일단 중복으로 간주하지 않거나 재시도할 수 있게 처리하지만,
        # 여기서는 False를 반환하여 삽입 시도하게 두고 DB 에러 로그를 남깁니다.
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
    
    # 1. 멱등성 검증 (Idempotency Check)
    if check_duplicate_log(user_key, timestamp):
        logger.info(f"중복된 로그 삽입 스킵: {user_key} at {timestamp}")
        return None

    # 2. 바인딩 삽입 (SQL Injection 방어)
    insert_query = """
        INSERT INTO ide_activity_logs (
            user_key, source_tool, timestamp, event_type, 
            task_name, duration_seconds, input_tokens, output_tokens, 
            raw_message, has_code_block
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    # 안전하게 값 할당. None이 들어갈 수 있는 부분 처리
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
        # isolation_level=None 이므로 수동 트랜잭션 시작 제어
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

def get_dashboard_stats(user_key: str) -> Dict[str, Any]:
    """
    Streamlit 프론트엔드 대시보드에서 렌더링할 통계 데이터를 SQLite에서 집계하여 반환합니다.
    - total_logs: 전체 누적 로그 건수
    - today_tokens: 오늘(UTC 기준) 사용된 전체 토큰 수 (input + output)
    - has_code_ratio: 전체 로그 중 코드 블록이 포함된 비율 (%)
    - trend_7d: 최근 7일 간의 날짜별 로그 발생 건수 (차트용)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. 전체 누적 건수
        cursor.execute("SELECT COUNT(id) FROM ide_activity_logs WHERE user_key = ?", (user_key,))
        total_logs = cursor.fetchone()[0] or 0
        
        # 2. 오늘 사용된 전체 토큰 수
        # timestamp는 YYYY-MM-DD HH:MM:SS 형식이므로, 오늘 날짜(YYYY-MM-DD)와 일치하는 것을 찾음
        cursor.execute("""
            SELECT SUM(input_tokens + output_tokens) 
            FROM ide_activity_logs 
            WHERE user_key = ? AND date(timestamp) = date('now', 'localtime')
        """, (user_key,))
        today_tokens = cursor.fetchone()[0] or 0
        
        # 3. 코드 블록 포함 비율
        cursor.execute("""
            SELECT COUNT(id) 
            FROM ide_activity_logs 
            WHERE user_key = ? AND has_code_block = 1
        """, (user_key,))
        code_blocks = cursor.fetchone()[0] or 0
        has_code_ratio = round((code_blocks / total_logs * 100), 1) if total_logs > 0 else 0.0
        
        # 4. 최근 7일 트렌드 (날짜별 발생 건수)
        # SQLite date 함수를 이용해 그룹화
        cursor.execute("""
            SELECT date(timestamp) as log_date, COUNT(id) as count
            FROM ide_activity_logs
            WHERE user_key = ? AND date(timestamp) >= date('now', '-6 days', 'localtime')
            GROUP BY log_date
            ORDER BY log_date ASC
        """, (user_key,))
        rows = cursor.fetchall()
        
        # 5. 에이전트 가동 상태 메트릭 (uptime, total_lines, total_bytes, last_sync_time)
        cursor.execute("""
            SELECT 
                MIN(timestamp) as first_log,
                MAX(timestamp) as last_log,
                SUM(LENGTH(raw_message) - LENGTH(REPLACE(IFNULL(raw_message, ''), CHAR(10), '')) + 1) as total_lines,
                SUM(LENGTH(IFNULL(raw_message, ''))) as total_bytes
            FROM ide_activity_logs 
            WHERE user_key = ?
        """, (user_key,))
        metric_row = cursor.fetchone()
        
        first_log = metric_row[0] if metric_row and metric_row[0] else None
        last_sync_time = metric_row[1] if metric_row and metric_row[1] else None
        total_lines = metric_row[2] if metric_row and metric_row[2] else 0
        total_bytes = metric_row[3] if metric_row and metric_row[3] else 0
        
        import datetime
        today = datetime.datetime.now().date()
        
        if first_log:
            try:
                first_date = datetime.datetime.strptime(first_log, "%Y-%m-%d %H:%M:%S").date()
                uptime_days = (today - first_date).days + 1
            except Exception:
                uptime_days = 1
        else:
            uptime_days = 0

        # 날짜 누락 방지: 최근 7일치 배열 강제 생성
        trend_7d = []
        date_counts = {row[0]: row[1] for row in rows}
        
        for i in range(6, -1, -1):
            d_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            trend_7d.append({
                "date": d_str,
                "count": date_counts.get(d_str, 0)
            })
            
        current_db_mb = get_total_db_size_mb()
        max_db_mb = 500.0
            
        return {
            "total_logs": total_logs,
            "today_tokens": today_tokens,
            "has_code_ratio": has_code_ratio,
            "trend_7d": trend_7d,
            "uptime_days": uptime_days,
            "total_lines": total_lines,
            "total_bytes": total_bytes,
            "last_sync_time": last_sync_time,
            "current_db_mb": round(current_db_mb, 2),
            "max_db_mb": max_db_mb
        }
    except sqlite3.Error as e:
        logger.error(f"대시보드 통계 집계 중 에러 발생: {e}")
        return {
            "total_logs": 0, "today_tokens": 0, "has_code_ratio": 0.0, "trend_7d": [],
            "uptime_days": 0, "total_lines": 0, "total_bytes": 0, "last_sync_time": None,
            "current_db_mb": 0.0, "max_db_mb": 500.0
        }
    finally:
        conn.close()

def get_total_db_size_mb() -> float:
    from backend.db.connection import get_db_path
    from backend.db.chroma_handler import get_chroma_dir
    import os

    total_bytes = 0
    
    # 1. SQLite 크기 측정
    sqlite_path = get_db_path()
    if os.path.exists(sqlite_path):
        total_bytes += os.path.getsize(sqlite_path)
        
    # 2. Chroma DB 디렉토리 크기 합산
    chroma_dir = get_chroma_dir()
    if os.path.exists(chroma_dir):
        for root, dirs, files in os.walk(chroma_dir):
            for file in files:
                total_bytes += os.path.getsize(os.path.join(root, file))
                
    return total_bytes / (1024 * 1024)

def cleanup_ttl_logs() -> list[int]:
    """
    7일이 지난 오래된 로그를 삭제하고 삭제된 레코드 ID 리스트를 반환합니다.
    """
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
    """
    용량 상한선에 도달했을 때 가장 오래된 로그를 삭제하고 삭제된 ID 리스트를 반환합니다.
    """
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
