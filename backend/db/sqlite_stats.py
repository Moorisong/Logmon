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
        
        cursor.execute("SELECT COUNT(id) FROM ide_activity_logs WHERE user_key = ?", (user_key,))
        total_logs = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT SUM(input_tokens + output_tokens) 
            FROM ide_activity_logs 
            WHERE user_key = ? AND date(timestamp) = date('now', 'localtime')
        """, (user_key,))
        today_tokens = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT COUNT(id) 
            FROM ide_activity_logs 
            WHERE user_key = ? AND has_code_block = 1
        """, (user_key,))
        code_blocks = cursor.fetchone()[0] or 0
        has_code_ratio = round((code_blocks / total_logs * 100), 1) if total_logs > 0 else 0.0
        
        cursor.execute("""
            SELECT date(timestamp) as log_date, COUNT(id) as count
            FROM ide_activity_logs
            WHERE user_key = ? AND date(timestamp) >= date('now', '-6 days', 'localtime')
            GROUP BY log_date
            ORDER BY log_date ASC
        """, (user_key,))
        rows = cursor.fetchall()
        
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
        
        cursor.execute("""
            SELECT event_type FROM ide_activity_logs 
            WHERE user_key = ? AND source_tool = 'Agent CLI' AND event_type IN ('AGENT_INSTALL', 'AGENT_UNINSTALL')
            ORDER BY timestamp DESC, id DESC LIMIT 1
        """, (user_key,))
        state_row = cursor.fetchone()
        if state_row:
            is_agent_installed = (state_row[0] == 'AGENT_INSTALL')
        else:
            cursor.execute("""
                SELECT COUNT(id) FROM ide_activity_logs 
                WHERE user_key = ? AND source_tool != 'Manual Upload UI'
            """, (user_key,))
            agent_logs_count = cursor.fetchone()[0] or 0
            is_agent_installed = agent_logs_count > 0
            
        # 에이전트 연결이 끊긴(삭제된) 상태라면 즉각 모든 통계를 0으로 처리 (사용자 요구사항 반영)
        if not is_agent_installed:
            return {
                "total_logs": 0,
                "today_tokens": 0,
                "has_code_ratio": 0.0,
                "trend_7d": [],
                "uptime_days": 0,
                "total_lines": 0,
                "total_bytes": 0,
                "last_sync_time": None,
                "current_db_mb": 0.0,
                "max_db_mb": 500.0,
                "is_agent_installed": False
            }
        
        first_log = metric_row[0] if metric_row and metric_row[0] else None
        last_sync_time = metric_row[1] if metric_row and metric_row[1] else None
        total_lines = metric_row[2] if metric_row and metric_row[2] else 0
        total_bytes = metric_row[3] if metric_row and metric_row[3] else 0
        
        today = datetime.datetime.now().date()
        
        if first_log:
            try:
                first_date = datetime.datetime.strptime(first_log, "%Y-%m-%d %H:%M:%S").date()
                uptime_days = (today - first_date).days + 1
            except Exception:
                uptime_days = 1
        else:
            uptime_days = 0

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
            "max_db_mb": max_db_mb,
            "is_agent_installed": is_agent_installed
        }
    except sqlite3.Error as e:
        logger.error(f"대시보드 통계 집계 중 에러 발생: {e}")
        return {
            "total_logs": 0, "today_tokens": 0, "has_code_ratio": 0.0, "trend_7d": [],
            "uptime_days": 0, "total_lines": 0, "total_bytes": 0, "last_sync_time": None,
            "current_db_mb": 0.0, "max_db_mb": 500.0, "is_agent_installed": False
        }
    finally:
        conn.close()
