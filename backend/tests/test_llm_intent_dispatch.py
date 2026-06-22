# backend/tests/test_llm_intent_dispatch.py
from __future__ import annotations
# SQLite Fallback 분기 의도(Intent) 처리 검증 테스트
# — test_llm_new_features.py 300줄 한도 준수를 위해 분리됨
import os
import shutil
import pytest
import respx
import httpx

# 테스트 환경 강제 분리
os.environ["LOGMON_ENV"] = "test"
os.environ["LOGMON_DB_DIR"] = "/tmp/logmon_test_intent_dispatch_db"
os.environ["LOGMON_CHROMA_DIR"] = "/tmp/logmon_test_intent_dispatch_chroma"

from backend.db.connection import init_db
from backend.llm.client import generate_completion, OLLAMA_HOST

# ──────────────────────────────────────────────────────────────
# 공통 Fixture
# ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_and_teardown():
    from backend.llm.memory import _conversation_memory
    _conversation_memory.clear()
    init_db()
    yield
    _conversation_memory.clear()
    if os.path.exists(os.environ["LOGMON_DB_DIR"]):
        shutil.rmtree(os.environ["LOGMON_DB_DIR"], ignore_errors=True)


# ──────────────────────────────────────────────────────────────
# 공통 헬퍼
# ──────────────────────────────────────────────────────────────

def _set_env_dev() -> str | None:
    """테스트 중 LOGMON_ENV를 'dev'로 전환하고 원래 값을 반환합니다."""
    original = os.environ.get("LOGMON_ENV")
    os.environ["LOGMON_ENV"] = "dev"
    return original


def _restore_env(original: str | None) -> None:
    """LOGMON_ENV를 원래 값으로 복원합니다."""
    if original is not None:
        os.environ["LOGMON_ENV"] = original
    else:
        os.environ.pop("LOGMON_ENV", None)


def _insert_error_log() -> None:
    """에러 로그 더미 데이터를 DB에 적재합니다."""
    from backend.db.sqlite_handler import insert_activity_log
    insert_activity_log({
        "user_key": "dev_test",
        "source_tool": "VSCode",
        "timestamp": "2026-06-22 09:00:00",
        "event_type": "ERROR",
        "task_name": "BUILD",
        "duration_seconds": 5,
        "input_tokens": 0,
        "output_tokens": 0,
        "raw_message": "ModuleNotFoundError: No module named 'requests'",
        "has_code_block": 0,
    })


def _insert_usage_log() -> None:
    """일반 활동(사용 시간/토큰) 더미 데이터를 DB에 적재합니다."""
    from backend.db.sqlite_handler import insert_activity_log
    insert_activity_log({
        "user_key": "dev_test",
        "source_tool": "VSCode",
        "timestamp": "2026-06-22 10:00:00",
        "event_type": "INFO",
        "task_name": "CODING",
        "duration_seconds": 3600,
        "input_tokens": 500,
        "output_tokens": 200,
        "raw_message": "File saved: main.py",
        "has_code_block": 0,
    })


# ──────────────────────────────────────────────────────────────
# 1. [로그/에러 분기] 의도 키워드 → 에러 개수 응답 포맷 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_err_log_intent_returns_count_format():
    """'로그 정리해봐' 등 로그/에러 키워드 질문 시 에러 개수 분기가 동작하여
    '총 {N}개임' 포맷을 반환하고, 시간/토큰 응답이 섞이지 않는지 검증."""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    respx.post(endpoint).mock(side_effect=httpx.ConnectError("Connection refused"))

    original = _set_env_dev()
    try:
        _insert_error_log()

        err_log_questions = [
            "에러 로그 정리해봐",
            "에러 몇 개야?",
            "오늘 오류 개수 알려줘",
        ]

        for question_text in err_log_questions:
            prompt = f"[과거 로그 컨텍스트]\n\n[사용자 질문]\n{question_text}\n[답변]"
            result = await generate_completion(prompt)

            assert "총" in result, (
                f"[로그/에러 분기] '총' 키워드 없음 — 질문='{question_text}', 응답={result}"
            )
            assert "개임" in result or "개." in result, (
                f"[로그/에러 분기] '개임/개.' 없음 — 질문='{question_text}', 응답={result}"
            )
            assert "사용 시간:" not in result, (
                f"[로그/에러 분기] 시간/토큰 응답이 잘못 반환됨 — 질문='{question_text}', 응답={result}"
            )
    finally:
        _restore_env(original)


# ──────────────────────────────────────────────────────────────
# 2. [시간/토큰 분기] 의도 키워드 → 누적 통계 응답 포맷 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_time_token_intent_returns_usage_format():
    """'오늘 사용 시간 알려줘' 등 시간/토큰 키워드 질문 시 누적 통계 분기가 동작하여
    '사용 시간:', 'AI 토큰량:' 포맷을 반환하고, 에러 개수 응답이 섞이지 않는지 검증."""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    respx.post(endpoint).mock(side_effect=httpx.ConnectError("Connection refused"))

    original = _set_env_dev()
    try:
        _insert_usage_log()

        time_token_questions = [
            "오늘 사용 시간 알려줘",
            "AI 토큰 얼마나 썼어?",
            "사용량 보여줘",
        ]

        for question_text in time_token_questions:
            prompt = f"[과거 로그 컨텍스트]\n\n[사용자 질문]\n{question_text}\n[답변]"
            result = await generate_completion(prompt)

            assert "사용 시간:" in result, (
                f"[시간/토큰 분기] '사용 시간:' 없음 — 질문='{question_text}', 응답={result}"
            )
            assert "AI 토큰량:" in result, (
                f"[시간/토큰 분기] 'AI 토큰량:' 없음 — 질문='{question_text}', 응답={result}"
            )
            assert "총" not in result or "개임" not in result, (
                f"[시간/토큰 분기] 에러 개수 응답이 잘못 반환됨 — 질문='{question_text}', 응답={result}"
            )
    finally:
        _restore_env(original)


# ──────────────────────────────────────────────────────────────
# 3. [크로스 오염 방지] 두 분기가 서로의 응답을 절대 반환하지 않는지 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_intent_dispatch_no_cross_contamination():
    """로그/에러 질문 → 시간 응답 X, 시간/토큰 질문 → 에러 개수 응답 X 를 동시에 검증."""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    respx.post(endpoint).mock(side_effect=httpx.ConnectError("Connection refused"))

    original = _set_env_dev()
    try:
        _insert_error_log()
        _insert_usage_log()

        # 로그 질문 → 반드시 에러 개수 포맷
        prompt_err = "[과거 로그 컨텍스트]\n\n[사용자 질문]\n에러 로그 정리해봐\n[답변]"
        result_err = await generate_completion(prompt_err)
        assert "사용 시간:" not in result_err, f"로그 질문에 시간 응답 크로스 오염: {result_err}"
        assert "총" in result_err, f"로그 질문에 에러 개수 표현 없음: {result_err}"

        # 시간 질문 → 반드시 사용량 포맷
        prompt_time = "[과거 로그 컨텍스트]\n\n[사용자 질문]\n오늘 사용 시간 알려줘\n[답변]"
        result_time = await generate_completion(prompt_time)
        assert "사용 시간:" in result_time, f"시간 질문에 사용 시간 표현 없음: {result_time}"
        assert "총" not in result_time or "개임" not in result_time, (
            f"시간 질문에 에러 개수 응답 크로스 오염: {result_time}"
        )
    finally:
        _restore_env(original)
