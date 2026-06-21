import re
from typing import Optional

# 로그 분석 핵심 키워드 리스트 (가드레일 우회용)
DEV_KEYWORDS = [
    "error", "warning", "warn", "log", "exception", "fail", "critical",
    "에러", "오류", "로그", "실패", "경고", "기록", "커밋", "빌드", "build",
    "db", "database", "connection", "host", "port", "커넥션", "호스트", "포트",
    "git", "깃", "sqlite", "chroma"
]

# 단순 인사, 비속어, 날씨, 일상 대화 차단 패턴
GUARDRAIL_PATTERNS = [
    r"^(안녕|안녕하세요|반가워|hi|hello)\b",
    r"(바보|멍청이|나쁜놈|시발|새끼|짜증|일 안 하냐)",
    r"^(뭐해|뭐하니|심심해|놀자)$",
    r"(날씨|기온|비 오나|눈 오나|비가|눈이|weather)",
    r"(노래|맛집|추천|심심한데)",
    r"(정체가 뭐야|뭐 하는 애|누구야|자기소개)"
]

def check_guardrail(question: str) -> Optional[str]:
    """
    사용자 입력이 로그 분석과 무관한 단순 채팅인지 검증합니다.
    개발/로그 관련 키워드가 포함된 질문은 가드레일을 통과시키며,
    그 외 불필요한 일상 질문은 LLM 호출 없이 즉시 명사형 안내 메시지를 반환합니다.
    """
    clean_q = question.strip().lower()
    
    # 개발/로그 관련 핵심 키워드가 포함되어 있다면 가드레일 통과
    if any(keyword in clean_q for keyword in DEV_KEYWORDS):
        return None
        
    if len(clean_q) < 2:
        return "질문이 너무 짧습니다. 분석하고 싶은 로그나 에러에 대해 구체적으로 말씀해 주세요."
        
    for pattern in GUARDRAIL_PATTERNS:
        if re.search(pattern, clean_q):
            return "Logmon AI 에이전트. 로그 및 에러 질문 전용."
            
    return None

