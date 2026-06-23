# backend/llm/fact_reporters.py
"""
Fast-track 팩트 보고 함수 모음.
SQLite DB를 직접 조회하여 간단한 통계/현황 문자열을 반환합니다.
"""
import re
import sqlite3
import logging

logger = logging.getLogger(__name__)

REAL_DB_PATH = "/app/data/logmon.db"


def get_db_connection():
    return sqlite3.connect(f"file:{REAL_DB_PATH}?mode=ro", uri=True, timeout=30.0)


def get_fact_token_report() -> str:
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT raw_message FROM ide_activity_logs "
                "WHERE timestamp >= date('now', 'localtime', '-1 days') "
                "AND raw_message LIKE '%chat messages%'"
            ).fetchall()
            cnt = sum(
                int(m.group(1))
                for r in rows
                if (m := re.search(r"with (\d+) chat messages", r[0]))
            )
            return f"📊 **[AI 인프라]** 최근 24시간 추정 토큰량: `{cnt * 250:,} tokens`임"
    except Exception:
        return "❌ 토큰 장애"


def get_fact_warning_report() -> str:
    try:
        with get_db_connection() as conn:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM ide_activity_logs "
                "WHERE timestamp >= date('now', 'localtime', '-3 days') "
                "AND (raw_message LIKE '%warn%' OR raw_message LIKE '%warning%')"
            ).fetchone()[0] or 0
            return f"⚠️ **[최근 3일 경고 정산]** 총 경고 건수: `{cnt}개`임"
    except Exception:
        return "❌ 경고 장애"


def get_fact_error_report() -> str:
    try:
        with get_db_connection() as conn:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM ide_activity_logs "
                "WHERE timestamp >= date('now', 'localtime', '-7 days') "
                "AND (raw_message LIKE '%error%' OR raw_message LIKE '%fail%')"
            ).fetchone()[0] or 0
            return f"🚨 **[최근 7일 에러 정산]** 총 에러 건수: `{cnt}개`임"
    except Exception:
        return "❌ 에러 장애"


def get_fact_activity_summary() -> str:
    try:
        with get_db_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM ide_activity_logs "
                "WHERE timestamp >= date('now', 'localtime', '-1 days')"
            ).fetchone()[0] or 0
            return f"📝 **[오늘 활동 요약]** 최근 24시간 로그: `{total}개`임"
    except Exception:
        return "❌ 활동 장애"


def get_fact_ide_uptime() -> str:
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT source_tool, COUNT(*) as cnt FROM ide_activity_logs "
                "WHERE timestamp >= date('now', 'localtime', '-1 days') "
                "GROUP BY source_tool ORDER BY cnt DESC LIMIT 5"
            ).fetchall()
            if not rows:
                return "📟 **[IDE 업타임]** 최근 24시간 IDE 활동 없음"
            lines = "\n".join([f"  - {r[0]}: {r[1]}건" for r in rows])
            return f"📟 **[IDE 업타임]** 최근 24시간 IDE별 활동:\n{lines}"
    except Exception:
        return "❌ IDE 업타임 장애"


def get_fact_git_summary() -> str:
    try:
        with get_db_connection() as conn:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM ide_activity_logs "
                "WHERE timestamp >= date('now', 'localtime', '-7 days') "
                "AND (raw_message LIKE '%git%' OR raw_message LIKE '%commit%')"
            ).fetchone()[0] or 0
            return f"🔀 **[Git 커밋 현황]** 최근 7일 Git 관련 로그: `{cnt}건`임"
    except Exception:
        return "❌ Git 장애"


def get_fact_network_db_errors() -> str:
    try:
        with get_db_connection() as conn:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM ide_activity_logs "
                "WHERE timestamp >= date('now', 'localtime', '-3 days') "
                "AND (raw_message LIKE '%network%' OR raw_message LIKE '%connection error%' "
                "     OR raw_message LIKE '%db error%' OR raw_message LIKE '%database error%')"
            ).fetchone()[0] or 0
            return f"🌐 **[네트워크/DB 에러]** 최근 3일 발생 건수: `{cnt}건`임"
    except Exception:
        return "❌ 네트워크/DB 에러 장애"
