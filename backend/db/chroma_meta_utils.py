# backend/db/chroma_meta_utils.py
"""
ChromaDB 메타데이터 처리 유틸리티.
로그 레벨 정규화, action_type 분류, timestamp 변환 함수를 제공합니다.
"""
import datetime
import logging

logger = logging.getLogger(__name__)

# action_type 분류 키워드 매핑
_ACTION_TYPE_KEYWORDS = {
    "network": ["network", "http", "connection", "timeout", "socket", "request"],
    "build": ["build", "compile", "webpack", "gradle", "maven", "빌드"],
    "git": ["git", "commit", "push", "pull", "merge", "branch"],
    "system": ["system", "cpu", "memory", "disk", "process", "kernel"],
}


def classify_action_type(raw_message: str) -> str:
    """raw_message에서 action_type을 분류합니다. 매칭 없으면 빈 문자열 반환."""
    if not raw_message:
        return ""
    text_lower = raw_message.lower()
    for action_type, keywords in _ACTION_TYPE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return action_type
    return ""


def timestamp_to_epoch(timestamp_str: str) -> int:
    """'YYYY-MM-DD HH:MM:SS' 형식의 타임스탬프 문자열을 Epoch(int)로 변환합니다."""
    if not timestamp_str:
        return 0
    try:
        dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return 0


def normalize_log_level(event_type: str, chunk_text: str) -> str:
    """
    event_type 또는 청크 텍스트에서 표준 log_level을 추출합니다.
    허용 값: INFO, ERROR, WARN, DEBUG
    """
    level_upper = (event_type or "").upper()
    if level_upper in ("ERROR", "CRITICAL"):
        return "ERROR"
    if level_upper in ("WARNING", "WARN"):
        return "WARN"
    if level_upper == "DEBUG":
        return "DEBUG"
    if level_upper == "INFO":
        return "INFO"
    # 청크 텍스트에서 추론
    text_lower = chunk_text.lower()
    if any(w in text_lower for w in ["[error]", "error:", "exception:", "fail", "오류"]):
        return "ERROR"
    if any(w in text_lower for w in ["[warning]", "warning:", "warn:", "경고"]):
        return "WARN"
    if any(w in text_lower for w in ["[debug]", "debug:"]):
        return "DEBUG"
    return "INFO"
