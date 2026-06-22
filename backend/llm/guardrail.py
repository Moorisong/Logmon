# backend/llm/guardrail.py
import re

DEV_KEYWORDS = {
    # 기존 키워드
    "error", "warning", "log", "db", "git", "docker", "port", "binding", "connection", "critical", "exception", "crash",
    "에러", "오류", "경고", "로그", "디비", "깃", "도커", "포트", "바인딩", "커넥션", "문제", "해결", "작업", "크래시",
    # IDE 관련
    "ide", "vscode", "intellij", "인텔리제이",
    # 실행/빌드 관련
    "실행", "시간", "컴파일", "빌드", "build", "run",
    # 인프라/통계 관련
    "토큰", "token", "api", "호출", "서버", "server", "호스트", "host", "컨테이너", "container",
    "상태", "status", "메모리", "memory", "cpu", "트래픽", "스케줄러", "배치"
}

GUARDRAIL_FALLBACK_MSG = "죄송합니다. 저는 Logmon 시스템 로그 및 장애 분석 전용 AI 에이전트입니다. 개발 및 로그 관련 질문에만 답변할 수 있습니다."

# Fuzzy 매칭용 정규식 패턴 리스트 (오타 및 유사어 대응)
FUZZY_PATTERNS = [
    r"경고로[그드]",       # 경고로그, 경고로드
    r"[에애]러로[그드]",     # 에러로그, 에러로드, 애러로그, 애러로드
    r"빌드로[그드]",       # 빌드로그, 빌드로드
    r"[에애]러",          # 에러, 애러 오타 대응
    r"워닝",              # warning 유사어
    r"디비"               # DB 유사어
]

def check_guardrail(question: str) -> bool:
    q_lower = question.lower()
    q_no_space = q_lower.replace(" ", "")
    
    # 1. 키워드 매칭 (질문 원본 및 공백 제거 텍스트 기준)
    for keyword in DEV_KEYWORDS:
        if keyword in q_lower or keyword in q_no_space:
            return True
            
    # 2. 정규식 패턴 매칭 (Fuzzy Match - 원본 및 공백 제거 텍스트 기준)
    for pattern in FUZZY_PATTERNS:
        if re.search(pattern, q_lower) or re.search(pattern, q_no_space):
            return True
            
    return False




