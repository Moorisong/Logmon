# backend/llm/ide_classifier.py
"""
IDE Signature Matcher
raw_message 텍스트를 파싱하여 source_ide 메타데이터를 분류하는 dict 기반 경량 분류기.
새 IDE 추가 시 IDE_SIGNATURE_MAP에 항목만 추가하면 됩니다.
"""

from typing import Dict, List, Tuple

# (우선순위 순) 서명 패턴 → source_ide 매핑
# 리스트 내 첫 번째 매칭에서 즉시 반환
IDE_SIGNATURE_MAP: List[Tuple[List[str], str]] = [
    (["antigravity", "antigravity ide"], "Antigravity IDE"),
    (["cursor-server", "cursor"], "cursor"),
    (["code helper", "vscode", "visual studio code"], "vscode"),
    (["idea.log", "jetbrains", "intellij", "pycharm", "webstorm", "goland"], "JetBrains"),
    (["windsurf"], "windsurf"),
    (["zed"], "zed"),
]

DEFAULT_SOURCE_IDE = "Unknown"


def classify_source_ide(raw_text: str) -> str:
    """
    raw_text에서 IDE 서명 패턴을 매칭하여 source_ide 문자열을 반환합니다.

    Args:
        raw_text: 로그 원본 텍스트 (raw_message 또는 source_tool)

    Returns:
        매칭된 IDE 식별자 문자열. 매칭 없을 시 'Unknown'.
    """
    if not raw_text:
        return DEFAULT_SOURCE_IDE

    text_lower = raw_text.lower()
    for signatures, ide_label in IDE_SIGNATURE_MAP:
        if any(sig in text_lower for sig in signatures):
            return ide_label

    return DEFAULT_SOURCE_IDE


def classify_source_ide_from_fields(source_tool: str, raw_message: str) -> str:
    """
    source_tool과 raw_message 두 필드를 순서대로 시도하여 IDE를 분류합니다.
    source_tool에서 먼저 매칭을 시도하고, Unknown이면 raw_message로 재시도합니다.

    Args:
        source_tool: DB의 source_tool 컬럼 값
        raw_message: DB의 raw_message 컬럼 값

    Returns:
        최종 source_ide 문자열.
    """
    ide = classify_source_ide(source_tool)
    if ide == DEFAULT_SOURCE_IDE:
        ide = classify_source_ide(raw_message)
    return ide
