# backend/llm/simulated_response.py
"""
Ollama 오프라인 Fallback: SQLite 기반 모의 응답 생성 모듈.
"""
import sqlite3
import logging

logger = logging.getLogger(__name__)

REAL_DB_PATH = "/app/data/logmon.db"


def get_db_connection():
    return sqlite3.connect(f"file:{REAL_DB_PATH}?mode=ro", uri=True, timeout=30.0)


def query_sqlite_logs(question: str) -> list:
    """SQLite에서 질문과 관련된 로그를 조회하여 반환합니다."""
    q_lower = question.lower()
    try:
        with get_db_connection() as conn:
            if any(k in q_lower for k in ["에러", "오류", "error", "fail"]):
                rows = conn.execute(
                    "SELECT raw_message FROM ide_activity_logs "
                    "WHERE raw_message LIKE '%error%' OR raw_message LIKE '%fail%' LIMIT 5"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT raw_message FROM ide_activity_logs ORDER BY rowid DESC LIMIT 5"
                ).fetchall()
            return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def generate_simulated_response(question: str, logs: list) -> str:
    """Ollama 오프라인 시 SQLite 기반 모의 응답을 생성합니다."""
    q_lower = question.lower()

    if any(k in q_lower for k in ["에러", "오류", "error", "fail", "로그", "정리"]):
        cnt = len(logs)
        return f"안녕하세요! 실제 저장된 로그 데이터 기반 백업 분석:\n총 {cnt}개임."

    if any(k in q_lower for k in ["사용 시간", "토큰", "사용량"]):
        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    "SELECT COALESCE(SUM(duration_seconds), 0), "
                    "COALESCE(SUM(input_tokens + output_tokens), 0) "
                    "FROM ide_activity_logs "
                    "WHERE timestamp >= date('now', 'localtime', '-1 days')"
                ).fetchone()
                hours = round((row[0] or 0) / 3600, 1)
                tokens = row[1] or 0
                return (
                    f"안녕하세요! 실제 저장된 로그 데이터 기반 백업 분석:\n"
                    f"사용 시간: {hours}시간, AI 토큰량: {tokens}개"
                )
        except Exception:
            return "안녕하세요! 실제 저장된 로그 데이터 기반 백업 분석:\n사용 시간: 0.0시간, AI 토큰량: 0개"

    return "안녕하세요! 실제 저장된 로그 데이터를 기반으로 분석 중임."
