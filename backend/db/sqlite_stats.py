import sqlite3
import logging
import datetime
import os
from typing import Dict, Any

from backend.db.connection import get_connection, get_db_path
from backend.db.chroma_handler import get_chroma_dir

logger = logging.getLogger(__name__)

def get_total_db_size_mb() -> float:
    total_bytes = 0
    sqlite_path = get_db_path()
    if os.path.exists(sqlite_path):
        total_bytes += os.path.getsize(sqlite_path)
    chroma_dir = get_chroma_dir()
    if os.path.exists(chroma_dir):
        for root, dirs, files in os.walk(chroma_dir):
            for file in files:
                total_bytes += os.path.getsize(os.path.join(root, file))
    return total_bytes / (1024 * 1024)

def get_dashboard_stats(user_key: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. 전체 로그 건수
        cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE user_key = ?", (user_key,))
        total_logs = cursor.fetchone()[0] or 0
        
        # 2. 오늘 토큰 수
        cursor.execute("""
            SELECT SUM(input_tokens + output_tokens) 
            FROM ide_activity_logs 
            WHERE user_key = ? AND timestamp >= date('now', 'start of day')
        """, (user_key,))
        today_tokens = cursor.fetchone()[0] or 0
        
        # 3. 코드 블록 비율
        cursor.execute("""
            SELECT COUNT(*) 
            FROM ide_activity_logs 
            WHERE user_key = ? AND has_code_block = 1
        """, (user_key,))
        code_blocks = cursor.fetchone()[0] or 0
        has_code_ratio = round((code_blocks / total_logs * 100), 1) if total_logs > 0 else 0.0
        
        # 4. 최근 7일 트렌드
        cursor.execute("""
            SELECT date(timestamp) as log_date, COUNT(*) as count
            FROM ide_activity_logs
            WHERE user_key = ? AND timestamp >= date('now', '-6 days')
            GROUP BY log_date
            ORDER BY log_date ASC
        """, (user_key,))
        rows = cursor.fetchall()
        
        # 5. 메트릭 계산
        cursor.execute("""
            SELECT 
                MIN(timestamp),
                MAX(timestamp),
                SUM(LENGTH(raw_message) - LENGTH(REPLACE(IFNULL(raw_message, ''), CHAR(10), '')) + 1),
                SUM(LENGTH(IFNULL(raw_message, '')))
            FROM ide_activity_logs 
            WHERE user_key = ?
        """, (user_key,))
        metric_row = cursor.fetchone()
        
        # 에이전트 설치 상태 확인
        cursor.execute("""
            SELECT COUNT(*) FROM ide_activity_logs 
            WHERE user_key = ? AND source_tool != 'Manual Upload UI'
        """, (user_key,))
        is_agent_installed = cursor.fetchone()[0] > 0

        # 데이터 정제
        first_log = metric_row[0] if metric_row and metric_row[0] else None
        last_sync = metric_row[1] if metric_row and metric_row[1] else None
        
        uptime_days = 0
        if first_log:
            try:
                first_date = datetime.datetime.strptime(first_log.split(' ')[0], "%Y-%m-%d").date()
                uptime_days = (datetime.datetime.now().date() - first_date).days + 1
            except:
                uptime_days = 1

        data = {
            "is_online": True,
            "total_logs": total_logs,
            "today_tokens": today_tokens or 0,
            "has_code_ratio": has_code_ratio,
            "trend_7d": [],
            "uptime_days": uptime_days,
            "total_lines": metric_row[2] if metric_row and metric_row[2] else 0,
            "total_bytes": metric_row[3] if metric_row and metric_row[3] else 0,
            "last_sync_time": last_sync,
            "server_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current_db_mb": round(get_total_db_size_mb(), 2),
            "max_db_mb": 500.0,
            "is_agent_installed": is_agent_installed
        }

        # 트렌드 데이터 채우기
        today = datetime.datetime.now().date()
        date_counts = {row[0]: row[1] for row in rows}
        for i in range(6, -1, -1):
            d_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            data["trend_7d"].append({"date": d_str, "count": date_counts.get(d_str, 0)})
            
        return data

    except Exception as e:
        logger.error(f"대시보드 통계 에러: {e}")
        return {
            "is_online": False, 
            "total_logs": 0, 
            "today_tokens": 0, 
            "has_code_ratio": 0.0,
            "trend_7d": [], 
            "uptime_days": 0, 
            "total_lines": 0, 
            "total_bytes": 0,
            "last_sync_time": None, 
            "server_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "current_db_mb": 0.0, 
            "max_db_mb": 500.0, 
            "is_agent_installed": False
        }
    finally:
        conn.close()