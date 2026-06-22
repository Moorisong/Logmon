# backend/llm/stats_db.py
import re
import logging
import datetime
import collections

logger = logging.getLogger(__name__)

def upsert_daily_statistics(user_key: str) -> None:
    """
    오늘 KST 기준의 사용 통계(총 사용시간, 사용 토큰 수, 레벨별 로그 총 개수, 에러 Top 3, 최초 실행 시간)를 
    집계하여 [STATISTICS] 성격의 로그로 SQLite 및 Chroma DB에 Upsert합니다.
    """
    from backend.db.connection import get_connection
    from backend.db.chroma_handler import process_and_store_vector, delete_vectors_by_log_ids
    
    timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
    kst_now = datetime.datetime.now(timezone_kst)
    today_str = kst_now.strftime("%Y-%m-%d")
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. 사용시간, 토큰 수, 최초 실행 시간 추출
        cursor.execute("""
            SELECT 
                SUM(duration_seconds),
                SUM(input_tokens + output_tokens),
                MIN(timestamp)
            FROM ide_activity_logs
            WHERE user_key = ? 
              AND date(timestamp) = date('now', 'localtime')
              AND task_name != 'STATISTICS'
        """, (user_key,))
        row = cursor.fetchone()
        
        total_duration = row[0] or 0
        total_tokens = row[1] or 0
        min_timestamp = row[2]
        
        total_usage_hours = round(total_duration / 3600.0, 1)
        first_launch_time = min_timestamp.split(" ")[1] if min_timestamp else "00:00:00"
        
        # 2. 레벨별 로그 개수 추출
        cursor.execute("""
            SELECT event_type, COUNT(id)
            FROM ide_activity_logs
            WHERE user_key = ?
              AND date(timestamp) = date('now', 'localtime')
              AND task_name != 'STATISTICS'
            GROUP BY event_type
        """, (user_key,))
        level_counts = {r[0]: r[1] for r in cursor.fetchall()}
        
        count_info = level_counts.get("INFO", 0)
        count_warn = level_counts.get("WARNING", 0) + level_counts.get("WARN", 0)
        count_error = level_counts.get("ERROR", 0) + level_counts.get("CRITICAL", 0)
        total_log_count = sum(level_counts.values())
        
        # 3. 에러 종류 빈도수 집계 (ERROR, CRITICAL 로그 대상)
        cursor.execute("""
            SELECT raw_message FROM ide_activity_logs
            WHERE user_key = ?
              AND date(timestamp) = date('now', 'localtime')
              AND event_type IN ('ERROR', 'CRITICAL')
              AND task_name != 'STATISTICS'
        """, (user_key,))
        error_msgs = [r[0] for r in cursor.fetchall() if r[0]]
        
        error_names = []
        for msg in error_msgs:
            matches = re.findall(r'([A-Za-z_]+Exception|[A-Za-z_]+Error|Connection \w+|Permission \w+|Timeout)', msg, re.IGNORECASE)
            if matches:
                error_names.extend([m.strip() for m in matches])
            else:
                first_line = msg.strip().split('\n')[0]
                clean_line = re.sub(r'[^A-Za-z0-9\s]', '', first_line)
                words = clean_line.split()
                if words:
                    error_names.append(" ".join(words[:2]))
                    
        counter = collections.Counter(error_names)
        top_errors = counter.most_common(3)
        top_error_str = ", ".join([f"{name}: {count}" for name, count in top_errors])
        if not top_error_str:
            top_error_str = "None"
            
        stat_message = f"""[STATISTICS] [DATE: {today_str}]
- Total_Usage_Time: {total_usage_hours} Hours
- Total_AI_Tokens_Used: {total_tokens} Tokens
- Total_Log_Count: {total_log_count} Cases (INFO: {count_info}, WARN: {count_warn}, ERROR: {count_error})
- Top_Error_Types: [{top_error_str}]
- First_Launch_Time: {first_launch_time}"""
        
        # 오늘 날짜의 기존 STATISTICS 레코드가 있는지 검사
        cursor.execute("""
            SELECT id FROM ide_activity_logs 
            WHERE user_key = ? 
              AND date(timestamp) = date('now', 'localtime')
              AND task_name = 'STATISTICS'
            LIMIT 1
        """, (user_key,))
        existing = cursor.fetchone()
        
        cursor.execute("BEGIN TRANSACTION;")
        if existing:
            log_id = existing[0]
            cursor.execute("""
                UPDATE ide_activity_logs
                SET raw_message = ?, timestamp = ?
                WHERE id = ?
            """, (stat_message, kst_now.strftime("%Y-%m-%d %H:%M:%S"), log_id))
        else:
            cursor.execute("""
                INSERT INTO ide_activity_logs (
                    user_key, source_tool, timestamp, event_type, 
                    task_name, duration_seconds, input_tokens, output_tokens, 
                    raw_message, has_code_block
                ) VALUES (?, 'SYSTEM', ?, 'INFO', 'STATISTICS', 0, 0, 0, ?, 0)
            """, (user_key, kst_now.strftime("%Y-%m-%d %H:%M:%S"), stat_message))
            log_id = cursor.lastrowid
            
        conn.commit()
        
        # Chroma DB 덮어쓰기 업데이트
        delete_vectors_by_log_ids([log_id])
        
        data_to_store = {
            "user_key": user_key,
            "timestamp": kst_now.strftime("%Y-%m-%d %H:%M:%S"),
            "source_tool": "SYSTEM",
            "event_type": "INFO",
            "raw_message": stat_message
        }
        process_and_store_vector(log_id, data_to_store)
        logger.info(f"당일 통계 요약 적재 성공 (log_id: {log_id}):\n{stat_message}")
        
    except Exception as e:
        logger.error(f"당일 통계 요약 적재 실패: {e}")
        try:
            conn.rollback()
        except:
            pass
    finally:
        conn.close()

def get_error_log_count(start_time: str, end_time: str) -> int:
    """
    지정된 기간(start_time ~ end_time) 사이에 발생한
    ERROR/CRITICAL 이벤트 로그 건수를 COUNT(*) 쿼리로 반환합니다.
    STATISTICS 집계 레코드는 제외하고 카운트합니다.

    Args:
        start_time: 조회 시작 시각 문자열 (예: "2026-06-20 00:00:00")
        end_time: 조회 종료 시각 문자열 (예: "2026-06-22 11:00:00")

    Returns:
        해당 기간의 에러 로그 총 건수 (정수)
    """
    from backend.db.connection import get_connection

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM ide_activity_logs
            WHERE timestamp BETWEEN ? AND ?
              AND event_type IN ('ERROR', 'CRITICAL')
              AND task_name != 'STATISTICS'
            """,
            (start_time, end_time),
        )
        row = cursor.fetchone()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"에러 로그 개수 쿼리 중 오류 발생: {e}")
        return 0
    finally:
        conn.close()


def get_period_usage_stats(start_time: str, end_time: str) -> dict:
    """
    지정된 기간(start_time ~ end_time) 사이의
    누적 사용 시간(초)과 AI 토큰량을 SUM 쿼리로 반환합니다.
    STATISTICS 집계 레코드는 제외하고 집계합니다.

    Args:
        start_time: 조회 시작 시각 문자열 (예: "2026-06-20 00:00:00")
        end_time: 조회 종료 시각 문자열 (예: "2026-06-22 11:00:00")

    Returns:
        {"total_hours": float, "total_tokens": int} 딕셔너리
    """
    from backend.db.connection import get_connection

    conn = get_connection()
    try:
        cursor = conn.cursor()
        # COALESCE로 SUM 결과 NULL → 0 치환: 지정 기간에 로그가 없을 때 TypeError 완전 차단
        cursor.execute(
            """
            SELECT COALESCE(SUM(duration_seconds), 0),
                   COALESCE(SUM(input_tokens + output_tokens), 0)
            FROM ide_activity_logs
            WHERE timestamp BETWEEN ? AND ?
              AND task_name != 'STATISTICS'
            """,
            (start_time, end_time),
        )
        row = cursor.fetchone()
        # Python 단 이중 방어: DB COALESCE 이후에도 None이 흘러올 경우를 대비
        total_sec = row[0] if (row and row[0] is not None) else 0
        total_tokens = row[1] if (row and row[1] is not None) else 0
        return {
            "total_hours": round(total_sec / 3600.0, 1),
            "total_tokens": int(total_tokens),
        }
    except Exception as e:
        logger.error(f"기간별 사용량 통계 쿼리 중 오류 발생: {e}")
        return {"total_hours": 0.0, "total_tokens": 0}
    finally:
        conn.close()


def get_latest_statistics_data(user_key: str = None) -> dict:
    """
    SQLite 데이터베이스에서 가장 최신 STATISTICS 로그 레코드를 조회하여
    사용시간, 토큰수 등 수치 팩트를 딕셔너리로 반환합니다.
    """
    from backend.db.connection import get_connection
    default_data = {
        "total_usage_hours": 0.0,
        "total_tokens": 0,
        "total_log_count": 0,
        "count_info": 0,
        "count_warn": 0,
        "count_error": 0,
        "date_str": datetime.datetime.now().strftime("%Y-%m-%d")
    }
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT raw_message, timestamp FROM ide_activity_logs WHERE task_name = 'STATISTICS'"
        params = []
        if user_key:
            query += " AND user_key = ?"
            params.append(user_key)
        query += " ORDER BY timestamp DESC LIMIT 1"
        cursor.execute(query, params)
        row = cursor.fetchone()
        if row:
            raw_message = row[0] or ""
            timestamp = row[1] or ""
            
            usage_match = re.search(r"Total_Usage_Time:\s*([\d.]+)\s*Hours", raw_message)
            tokens_match = re.search(r"Total_AI_Tokens_Used:\s*(\d+)\s*Tokens", raw_message)
            log_count_match = re.search(
                r"Total_Log_Count:\s*(\d+)\s*Cases\s*\(INFO:\s*(\d+),\s*WARN:\s*(\d+),\s*ERROR:\s*(\d+)\)",
                raw_message
            )
            date_match = re.search(r"\[DATE:\s*([\d-]+)\]", raw_message)
            
            data = default_data.copy()
            if usage_match:
                data["total_usage_hours"] = float(usage_match.group(1))
            if tokens_match:
                data["total_tokens"] = int(tokens_match.group(1))
            if log_count_match:
                data["total_log_count"] = int(log_count_match.group(1))
                data["count_info"] = int(log_count_match.group(2))
                data["count_warn"] = int(log_count_match.group(3))
                data["count_error"] = int(log_count_match.group(4))
            if date_match:
                data["date_str"] = date_match.group(1)
            elif timestamp:
                data["date_str"] = timestamp.split(" ")[0]
                
            return data
    except Exception as e:
        logger.error(f"최신 통계 쿼리 중 오류 발생: {e}")
    finally:
        conn.close()
        
    return default_data
