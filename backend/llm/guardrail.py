from typing import Optional

# 로그 분석 핵심 키워드 리스트 (가드레일 우회용)
DEV_KEYWORDS = {
    # 영어 기술 키워드 (소문자 변환 후 비교 필수)
    "error", "warning", "warn", "log", "db", "git", "docker", "port", "binding", "connection", "critical", "exception", "fail", "sqlite", "chroma", "build", "host",
    # 한글 기술 키워드
    "에러", "오류", "경고", "로그", "디비", "깃", "도커", "포트", "바인딩", "커넥션", "문제", "해결", "작업", "실패", "기록", "커밋", "빌드", "호스트"
}

def check_guardrail(question: str) -> Optional[str]:
    """
    질문에 개발/로그 관련 키워드가 하나도 없으면 즉시 RAG 파이프라인 우회 응답을 반환합니다.
    """
    clean_q = question.strip().lower()
    
    # 개발/로그 관련 핵심 키워드가 하나라도 포함되어 있는지 검사
    if any(keyword in clean_q for keyword in DEV_KEYWORDS):
        if len(clean_q) < 2:
            return "질문이 너무 짧습니다. 분석하고 싶은 로그나 에러에 대해 구체적으로 말씀해 주세요."
        return None
        
    # 기술 키워드가 아예 없는 경우: 즉시 차단 메시지 반환
    return "최근 기록된 작업 로그가 존재하지 않습니다."


