# backend/llm/router.py
"""
Hybrid Query Router
사용자 질문을 분석하여 Fast-track(Regex DB 직접 조회) 또는
LLM Fallback(LLM이 키워드+메타데이터 필터를 추출)으로 라우팅합니다.

[설계 원칙]
- 복합 단순 통계 질문(개수/건수/현황) → Fast-track (DB 직접 조회)
- 맥락/분석/상세/이유 등 추론 요청 → LLM Fallback (ChromaDB RAG)
- Fast-track 규칙은 상위 순서부터 우선 적용됨 (순서 중요)
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────

ROUTE_FAST_TRACK = "fast_track"
ROUTE_LLM_FALLBACK = "llm_fallback"

# 복잡한 분석/추론 질문 감지 패턴 — 이 패턴에 해당하면 Fast-track 진입 차단.
# [포함 기준] 단순 집계로 답할 수 없는 추론/원인/상세 분석 동사·명사만 포함.
# [제외 기준] "알려줘", "보여줘", "요약", "정리해" 등 단순 요청 동사는 제외:
#             이 표현들은 단순 카운트 질문("경고 건수 알려줘")에도 쓰이기 때문.
_COMPLEX_ANALYSIS_PATTERN = re.compile(
    r"(상세\s*분석|원인\s*분석|이유\s*분석"          # 복합 분석 표현
    r"|분석해\s*줘|분석해\s*봐|분석해\s*보자"        # 분석 요청 동사
    r"|\b왜\b|\b이유\b|\b원인\b"                    # 원인 추론
    r"|\b어떻게\b|\b패턴\b|\b상세\b)",               # 세부 추론
    re.IGNORECASE,
)

# Fast-track 매핑 테이블: (정규식, route_key)
# ─ 순서 중요: 더 구체적(복합) 패턴을 앞에, 일반 패턴을 뒤에 배치
# ─ network_db는 connection error 등 복합 구문 포함 → error 단독 패턴보다 앞에 위치
_FAST_TRACK_RULES: List[tuple] = [
    # 1. 토큰 사용량 (가장 구체적)
    (re.compile(r"\b(토큰|token)\b", re.IGNORECASE), "token"),
    # 2. 네트워크/DB 에러 (복합 패턴 — error 단독보다 앞)
    (re.compile(
        r"(\bnetwork\b|\b네트워크\b|\bdb\s*에러\b|\b데이터베이스\s*에러\b"
        r"|\bconnection\s*error\b|\bconnection\b.*\b에러\b|\bnetwork\b.*\b에러\b)",
        re.IGNORECASE,
    ), "network_db"),
    # 3. 경고 단독 카운트
    (re.compile(r"\b(경고|warn(?:ing)?)\b", re.IGNORECASE), "warning"),
    # 4. 에러/오류 단독 카운트
    (re.compile(r"\b(에러|오류|error|fail(?:ure)?)\b", re.IGNORECASE), "error"),
    # 5. 전체 활동 요약 (개수/몇개 등) — IDE 관련 활동은 ide_uptime이 처리하므로 제외
    (re.compile(r"\b(개수|몇\s*개|몇\s*건|요약|전체|7일)\b", re.IGNORECASE), "activity"),
    # 6. IDE 업타임 — ide/에디터/프로그램/종류 단독 + 활동/업타임 포함 복합
    (re.compile(r"\b(ide|에디터|프로그램|종류|활동)\b", re.IGNORECASE), "ide_uptime"),
    # 7. Git 커밋 현황
    (re.compile(r"\b(git|커밋|commit)\b", re.IGNORECASE), "git"),
]

# LLM Fallback 시 사용하는 Few-shot 프롬프트 템플릿
LLM_FILTER_EXTRACTION_PROMPT = """당신은 로그 검색 전문 파서입니다.
사용자 질문에서 ChromaDB 검색에 필요한 키워드와 메타데이터 필터를 추출하세요.

[출력 규칙]
- keywords: 검색할 핵심 키워드 목록 (쉼표 구분)
- log_level: INFO / ERROR / WARN / DEBUG 중 해당하는 것 (없으면 빈 값)
- source_ide: Antigravity IDE / cursor / vscode / JetBrains / windsurf / zed 중 해당하는 것 (없으면 빈 값)
- action_type: network / build / git / system 중 해당하는 것 (없으면 빈 값)

[Few-shot 예시]

Q: 어제 JetBrains에서 발생한 빌드 에러 알려줘
A:
keywords: build, error, exception
log_level: ERROR
source_ide: JetBrains
action_type: build

Q: Cursor에서 git push 실패한 내역
A:
keywords: git, push, fail
log_level: ERROR
source_ide: cursor
action_type: git

Q: 오늘 네트워크 타임아웃 경고
A:
keywords: network, timeout, warn
log_level: WARN
source_ide:
action_type: network

[실제 질문]
Q: {question}
A:"""


@dataclass
class RouteResult:
    """라우팅 결과를 담는 불변 데이터 클래스."""
    route: str                            # ROUTE_FAST_TRACK | ROUTE_LLM_FALLBACK
    fast_track_key: Optional[str] = None  # 빠른 경로 식별 키
    keywords: List[str] = field(default_factory=list)
    log_level: str = ""
    source_ide: str = ""
    action_type: str = ""


def detect_fast_track(question: str) -> Optional[RouteResult]:
    """
    Regex 기반 Fast-track 매칭을 시도합니다.

    [우선순위 로직]
    1. 분석/추론 복합 질문이면 즉시 None 반환 (LLM Fallback 강제)
    2. Fast-track 규칙 테이블 순서대로 매칭 시도
    3. 첫 매칭에서 RouteResult(route=ROUTE_FAST_TRACK) 반환
    4. 매칭 실패 시 None 반환

    Args:
        question: 사용자 원본 질문 텍스트

    Returns:
        RouteResult (fast-track) 또는 None (LLM Fallback)
    """
    # 복잡 분석 질문은 Fast-track 차단 → LLM Fallback으로 보냄
    if _COMPLEX_ANALYSIS_PATTERN.search(question):
        logger.info(f"[Router] 분석/추론 질문 감지 → LLM Fallback 강제: '{question}'")
        return None

    q_lower = question.lower()
    for pattern, route_key in _FAST_TRACK_RULES:
        if pattern.search(q_lower):
            logger.info(f"[Router] Fast-track 매칭: key={route_key}, 질문='{question}'")
            return RouteResult(route=ROUTE_FAST_TRACK, fast_track_key=route_key)
    return None


def parse_llm_filter_response(llm_response: str) -> Dict[str, Any]:
    """
    LLM이 반환한 필터 추출 텍스트를 파싱하여 dict로 변환합니다.
    파싱 실패 시 빈 dict를 안전하게 반환합니다.
    """
    result: Dict[str, Any] = {
        "keywords": [],
        "log_level": "",
        "source_ide": "",
        "action_type": "",
    }
    if not llm_response:
        return result

    for line in llm_response.splitlines():
        line = line.strip()
        if line.startswith("keywords:"):
            raw = line.split("keywords:", 1)[-1].strip()
            result["keywords"] = [k.strip() for k in raw.split(",") if k.strip()]
        elif line.startswith("log_level:"):
            result["log_level"] = line.split("log_level:", 1)[-1].strip().upper()
        elif line.startswith("source_ide:"):
            result["source_ide"] = line.split("source_ide:", 1)[-1].strip()
        elif line.startswith("action_type:"):
            result["action_type"] = line.split("action_type:", 1)[-1].strip().lower()

    return result


def build_llm_fallback_prompt(question: str) -> str:
    """LLM 필터 추출 프롬프트를 생성합니다."""
    return LLM_FILTER_EXTRACTION_PROMPT.format(question=question)
