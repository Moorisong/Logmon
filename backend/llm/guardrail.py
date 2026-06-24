import re
import logging

logger = logging.getLogger(__name__)

# 파이썬 레벨에서 검출 시 LLM 호출 없이 즉시 반환할 단호한 템플릿 대답
GUARDRAIL_FALLBACK_MSG = "본 시스템은 IDE 내부 코딩 활동(몰입도, AI 도구 활용, 에러 디버깅, 파일 작업)에 특화되어 있습니다. 해당 범주 내의 질문을 해주시면 상세히 분석해 드리겠습니다."

# 띄어쓰기를 완전히 무시하고 매칭하기 위해 공백을 제거한 소문자 형태의 블랙리스트 키워드 세트입니다.
FORBIDDEN_KEYWORDS = {
    # Git 및 원격 저장소 활동 관련
    "git", "깃", "push", "푸시", "푸쉬", "commit", "커밋", "pull", "풀", "merge", "머지", 
    "clone", "클론", "github", "깃헙", "깃허브", "gitlab", "깃랩", "fetch", "페치", "브랜치", "branch",
    
    # 가상화, 인프라 및 OS 시스템 환경 관련
    "docker", "도커", "container", "컨테이너", "kubernetes", "쿠버네티스", "k8s", "aws", "gcp", "azure", 
    "터미널", "terminal", "cmd", "명령프롬프트", "powershell", "파워쉘", "shell", "쉘", "linux", "리눅스",
    
    # 일반 웹, 미디어 및 딴짓/소통 도구 관련
    "youtube", "유튜브", "netflix", "넷플릭스", "game", "게임", "slack", "슬랙", "discord", "디스코드", 
    "카톡", "카카오톡", "메신저", "teams", "팀즈", "chrome", "크롬", "safari", "사파리", "browser", 
    "브라우저", "구글링", "검색", "웹서핑", "인터넷"
}

# 3대 핵심 가치 지표 화이트리스트 키워드 (확장됨)
CORE_KEYWORDS = {
    "error", "warning", "log", "exception", "crash", "traceback", "fail", "typeerror",
    "에러", "오류", "경고", "로그", "크래시", "트레이스백", "실패",
    "token", "토큰", "ai", "assist", "copilot", "cloudcode", "assistant", "올라마", "ollama",
    "workspace", "active", "save", "coding", "코딩", "몰입", "저장", "시간", "수정", "작업",
    # 파일 및 경로 관련 추가
    "file", "path", "open", "read", "view", "edit", "name",
    "파일", "경로", "열어본", "수정한", "이름", "작성"
}

def check_guardrail(question: str) -> bool:
    """
    사용자의 질문을 검사하여 외부 활동 분석 요청을 파이썬 선에서 선제 차단합니다.
    안전한 질문이면 True, 차단해야 할 외부 도구 질문이면 False를 반환합니다.
    """
    q_lower = question.lower().strip()
    
    # 0. 단순 인사말 패스
    GREETING_PATTERNS = [
        r"^(하이|안녕|반가워|헬로|hi|hello|hey|어이|여보세요)[\s!?~]*$"
    ]
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, q_lower):
            return True

    # 1. 공백과 특수문자를 전부 트림 처리하여 우회 시도 차단
    q_trimmed = re.sub(r'[\s\-_,\./\\\*&^%$#@!~`?+=?|]', '', q_lower)

    # 2. 블랙리스트 검사
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in q_trimmed:
            logger.warning(f"🚫 [Guardrail 차단] 외부 도구 키워드 감지됨: '{keyword}' (원본 질문: {question})")
            return False

    # 3. 화이트리스트 보완 검사
    has_core_context = False
    for core_word in CORE_KEYWORDS:
        if core_word in q_lower or core_word in q_trimmed:
            has_core_context = True
            break
            
    if not has_core_context:
        logger.warning(f"🚫 [Guardrail 차단] 3대 핵심 지표와 무관한 일반 질문 필터링 (원본 질문: {question})")
        return False

    return True