from collections import deque
from typing import Dict

# Window Memory: user_key를 키로 하고, 최근 대화(질문, 답변) 내역을 deque로 관리
_conversation_memory: Dict[str, deque] = {}

def get_conversation_context(user_key: str, max_history: int = 3) -> str:
    """
    최근 3회 내외의 대화 기록을 포맷팅하여 반환합니다.
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

def add_conversation(user_key: str, question: str, answer: str, max_history: int = 3):
    """
    질문과 답변 쌍을 메모리에 추가합니다.
    """
    if user_key not in _conversation_memory:
        _conversation_memory[user_key] = deque(maxlen=max_history)
        
    _conversation_memory[user_key].append((question, answer))
