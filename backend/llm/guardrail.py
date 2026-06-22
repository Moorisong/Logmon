# backend/llm/guardrail.py

DEV_KEYWORDS = {
    "error", "warning", "log", "db", "git", "docker", "port", "binding", "connection", "critical", "exception",
    "에러", "오류", "경고", "로그", "디비", "깃", "도커", "포트", "바인딩", "커넥션", "문제", "해결", "작업"
}

GUARDRAIL_FALLBACK_MSG = "죄송합니다. 저는 Logmon 시스템 로그 및 장애 분석 전용 AI 에이전트입니다. 개발 및 로그 관련 질문에만 답변할 수 있습니다."

def check_guardrail(question: str) -> bool:
    q_lower = question.lower()
    return any(keyword in q_lower for keyword in DEV_KEYWORDS)



