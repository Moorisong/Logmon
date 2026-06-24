# backend/llm/memory.py
import logging
from collections import deque
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# 슬라이딩 윈도우 메모리 유지 (상태 유지용)
_conversation_memory: Dict[str, deque] = {}
DEFAULT_MAX_HISTORY = 2

def get_conversation_context(user_key: str) -> str:
    """
    이제 이 함수는 프롬프트에 자동 주입되지 않습니다.
    사용자가 '이전 대화와 연결해서 알려줘'라고 명시할 때만 호출하여 사용하십시오.
    """
    if user_key not in _conversation_memory:
        return ""
        
    history = _conversation_memory[user_key]
    if not history:
        return ""
        
    context_lines = [f"User: {q}\nAI: {a}" for q, a in history]
    return "\n\n".join(context_lines)

def add_conversation(user_key: str, question: str, answer: str, max_history: int = DEFAULT_MAX_HISTORY) -> None:
    """
    대화 내용은 메모리에 적재하되, 모델이 과거 답변을 복사하는 것을 방지하기 위해 
    프롬프트에는 직접 주입하지 않고 시스템 상태로만 관리합니다.
    """
    if user_key not in _conversation_memory:
        _conversation_memory[user_key] = deque(maxlen=max_history)
        
    _conversation_memory[user_key].append((question, answer))
    logger.debug(f"사용자 [{user_key}] 메모리 적재 완료 (Stateless 모드)")

def clear_memory(user_key: str) -> None:
    if user_key in _conversation_memory:
        _conversation_memory[user_key].clear()
        logger.info(f"사용자 [{user_key}] 메모리 클리어")