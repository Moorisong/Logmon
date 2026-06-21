import re
from typing import Optional

# 불용어, 단순 인사, 욕설 패턴
GUARDRAIL_PATTERNS = [
    r"^(안녕|안녕하세요|hi|hello)\b",
    r"(바보|멍청이|나쁜놈|시발|새끼)",
    r"^(뭐해|뭐하니|심심해)$"
]

def check_guardrail(question: str) -> Optional[str]:
    """
    사용자 입력이 로그 분석과 무관한 단순 채팅인지 검증합니다.
    불필요한 경우 LLM 호출을 막고 즉시 안내 메시지를 반환합니다.
    """
    clean_q = question.strip().lower()
    
    if len(clean_q) < 2:
        return "질문이 너무 짧습니다. 분석하고 싶은 로그나 에러에 대해 구체적으로 말씀해 주세요."
        
    for pattern in GUARDRAIL_PATTERNS:
        if re.search(pattern, clean_q):
            return "안녕하세요! 저는 로컬 환경 로그 분석에 특화된 Logmon AI 에이전트입니다. 발생한 에러나 과거 작업 기록에 대해 질문해 주세요."
            
    return None
