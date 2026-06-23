import logging
from collections import deque
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# Window Memory: user_key를 키로 하고, 최근 대화(질문, 답변) 쌍을 고정 크기 deque로 관리
_conversation_memory: Dict[str, deque] = {}

# Llama 1B 경량 모델의 컨텍스트 왜곡을 방지하기 위한 기본 대화 기억 세트 수
DEFAULT_MAX_HISTORY = 3

def get_conversation_context(user_key: str) -> str:
    """
    특정 사용자의 최근 대화 기록을 프롬프트 주입용 텍스트로 정렬하여 반환합니다.
    """
    if user_key not in _conversation_memory:
        return ""
        
    history = _conversation_memory[user_key]
    if not history:
        return ""
        
    context_lines = []
    for q, a in history:
        context_lines.append(f"User: {q}\nAI: {a}")
        
    return "\n\n".join(context_lines)

def add_conversation(user_key: str, question: str, answer: str, max_history: int = DEFAULT_MAX_HISTORY) -> None:
    """
    새로운 질문과 답변 쌍을 메모리에 적재합니다. 
    지정된 max_history(기본 3개)를 초과하면 가장 오래된 세트가 자동으로 폐기됩니다.
    """
    if user_key not in _conversation_memory:
        # deque의 maxlen을 지정하면 파이썬 레벨에서 자동으로 FIFO(First-In-First-Out) 슬라이딩 윈도우가 보장됩니다.
        _conversation_memory[user_key] = deque(maxlen=max_history)
        
    _conversation_memory[user_key].append((question, answer))
    logger.debug(f"사용자 [{user_key}] 대화 메모리 업데이트 완료 (현재 윈도우 크기: {len(_conversation_memory[user_key])}/{max_history})")

def clear_memory(user_key: str) -> None:
    """
    특정 사용자의 대화 메모리를 완전히 비웁니다. (에이전트 언인스톨 또는 초기화용)
    """
    if user_key in _conversation_memory:
        _conversation_memory[user_key].clear()
        logger.info(f"사용자 [{user_key}] 대화 윈도우 메모리 클리어 완료")