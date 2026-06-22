# backend/tests/test_llm_new_features.py
import os
import shutil
import pytest
import datetime
import respx
import httpx
from unittest.mock import patch

# 테스트 환경 강제 분리
os.environ["LOGMON_ENV"] = "test"
os.environ["LOGMON_DB_DIR"] = "/tmp/logmon_test_llm_new_features_db"
os.environ["LOGMON_CHROMA_DIR"] = "/tmp/logmon_test_llm_new_features_chroma"

from backend.db.connection import init_db
from backend.llm.utils import parse_relative_datetime, manage_context_token_limit, postprocess_noun_ending
from backend.llm.client import generate_completion, OLLAMA_HOST, MODEL_NAME
from backend.llm.rag_engine import ask_rag_agent
from backend.llm.prompt_templates import COUNT_PROMPT_TEMPLATE
from backend.llm.guardrail import check_guardrail


@pytest.fixture(autouse=True)
def setup_and_teardown():
    from backend.llm.memory import _conversation_memory
    _conversation_memory.clear()
    init_db()
    yield
    _conversation_memory.clear()
    if os.path.exists(os.environ["LOGMON_DB_DIR"]):
        shutil.rmtree(os.environ["LOGMON_DB_DIR"], ignore_errors=True)


# 1-A. 상대 기간 날짜 파서 - 지난 2일
def test_parse_relative_datetime_past_two_days():
    """지난 2일 동안 질문 입력 시 KST 기준 정상 파싱 여부 검증"""
    start_time, end_time = parse_relative_datetime("지난 2일 동안 발생한 에러 보여줘")
    assert start_time is not None
    assert end_time is not None
    assert start_time.endswith("00:00:00")
    start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    delta = end_dt - start_dt
    assert 1.9 <= delta.days <= 2.1


# 1-B. 상대 기간 날짜 파서 - 일주일
def test_parse_relative_datetime_one_week():
    """일주일 동안 질문 입력 시 KST 기준 정상 파싱 여부 검증"""
    start_time, end_time = parse_relative_datetime("일주일 동안의 빌드 로그 요약해줘")
    assert start_time is not None
    assert end_time is not None
    assert start_time.endswith("00:00:00")
    start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    delta = end_dt - start_dt
    assert 6.9 <= delta.days <= 7.1


# 1-C. 상대 기간 날짜 파서 - 일반 질문 fallback
def test_parse_relative_datetime_fallback():
    """매칭되지 않는 일반 질문 입력 시 None 반환 검증"""
    start_time, end_time = parse_relative_datetime("그냥 일반적인 기술 질문")
    assert start_time is None
    assert end_time is None


# 2. 모델명 검증
@pytest.mark.asyncio
@respx.mock
async def test_llm_client_uses_llama_model():
    """Ollama API 호출 시 모델 이름이 llama3.2:1b로 설정되어 전송되는지 검증"""
    base = OLLAMA_HOST.rstrip("/")
    endpoint = f"{base}/api/generate"
    mock_route = respx.post(endpoint).mock(
        return_value=httpx.Response(200, json={"response": "Llama Answer"})
    )
    assert MODEL_NAME == "llama3.2:1b"
    result = await generate_completion("테스트용 프롬프트")
    assert result == "Llama Answer"
    import json
    payload = json.loads(mock_route.calls.last.request.content)
    assert payload["model"] == "llama3.2:1b"


# 3. 컨텍스트 압축 검증
def test_manage_context_token_limit_truncation():
    """매우 긴 컨텍스트 주입 시 1,800 토큰 이하로 압축되는지 검증"""
    docs = [
        "RawMessage: " + ("a" * 2000),
        "RawMessage: " + ("b" * 2000),
        "RawMessage: " + ("c" * 2000)
    ]
    context_str = manage_context_token_limit(
        docs=docs,
        question="전체 로그 요약",
        final_question="전체 로그 요약",
        selected_template=COUNT_PROMPT_TEMPLATE,
        current_date_str="2026-06-22"
    )
    assert "a" in context_str
    assert "b" in context_str
    assert "c" in context_str
    prompt = COUNT_PROMPT_TEMPLATE.format(
        current_date="2026-06-22",
        context=context_str,
        question="전체 로그 요약"
    )
    from backend.llm.utils import estimate_tokens
    assert estimate_tokens(prompt) <= 1800


# 4. STATISTICS 누락 방어 동작 검증
@pytest.mark.asyncio
@patch('backend.llm.rag_engine.query_vectors')
@patch('backend.llm.rag_engine.generate_completion')
async def test_ask_rag_agent_statistics_none_fallback(mock_generate, mock_query):
    """STATISTICS 없는 컨텍스트 수신 시 에러 없이 정상 진행 검증"""
    mock_query.return_value = [[
        "[2026-06-22 10:00:00] [ERROR] DB query connection timeout error"
    ]]
    mock_generate.return_value = "통계 처리 응답 성공"
    answer = await ask_rag_agent("오늘 에러 몇 개 발생했어?", "test_user")
    assert answer == "통계 처리 응답 성공"
    prompt_sent = mock_generate.call_args[0][0]
    assert "[Calculated Statistics]" not in prompt_sent


# 5. 어미 치환 보존 검증
def test_postprocess_noun_ending_advanced_safety():
    """안녕하세요, 보세요 등 보존어가 훼손되지 않는지 검증"""
    assert postprocess_noun_ending("안녕하세요. 반가워요.") == "안녕하세요. 반가워."
    assert postprocess_noun_ending("작업이 필요요망.") == "작업이 필요요망."
    assert postprocess_noun_ending("디버깅해 보세요.") == "디버깅해 보세요."
    assert postprocess_noun_ending("데이터가 필요합니다.") == "데이터가 필요함."


# 6. [에러/로그 분기] 의도 질문 시 '총 N개임.' 패턴 반환 검증
@pytest.mark.asyncio
@respx.mock
async def test_simulated_err_log_intent_returns_count_pattern():
    """
    Ollama 오프라인 상태에서 로그/에러 개수 의도 질문 시
    '총 N개임.' 패턴 응답이 반환되어야 함 (의도 분기 문자열 검증)
    """
    base = OLLAMA_HOST.rstrip("/")
    endpoint = f"{base}/api/generate"
    respx.post(endpoint).mock(side_effect=httpx.ConnectError("Connection refused"))
    original_env = os.environ.get("LOGMON_ENV")
    os.environ["LOGMON_ENV"] = "dev"
    try:
        from backend.db.sqlite_handler import insert_activity_log
        insert_activity_log({
            "user_key": "dev_test",
            "source_tool": "VSCode",
            "timestamp": "2026-06-22 10:00:00",
            "event_type": "ERROR",
            "task_name": "CODING",
            "duration_seconds": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "raw_message": "TypeError: Cannot read property of undefined",
            "has_code_block": 0
        })
        err_log_questions = [
            "에러 로그 정리해봐",
            "에러 몇 개야?",
            "오류 개수 알려줘",
            "에러 건수 몇 건이야?",
        ]
        for q in err_log_questions:
            prompt = "[과거 로그 컨텍스트]\n\n[사용자 질문]\n" + q + "\n[답변]"
            result = await generate_completion(prompt)
            assert "총" in result, f"[에러/로그 분기] 총 없음 - 질문={q}, 응답={result}"
            assert "개임" in result, f"[에러/로그 분기] 개임 없음 - 질문={q}, 응답={result}"
            assert "사용 시간:" not in result, f"[에러/로그 분기] 시간 분기 오반환 - 질문={q}, 응답={result}"
    finally:
        if original_env is not None:
            os.environ["LOGMON_ENV"] = original_env
        else:
            del os.environ["LOGMON_ENV"]


# 7. [시간/토큰 분기] 의도 질문 시 '사용 시간: N시간, AI 토큰량: N개' 패턴 반환 검증
@pytest.mark.asyncio
@respx.mock
async def test_simulated_time_token_intent_returns_usage_pattern():
    """
    Ollama 오프라인 상태에서 시간/토큰 의도 질문 시
    '사용 시간: N시간, AI 토큰량: N개' 패턴 응답이 반환되어야 함 (의도 분기 문자열 검증)
    """
    base = OLLAMA_HOST.rstrip("/")
    endpoint = f"{base}/api/generate"
    respx.post(endpoint).mock(side_effect=httpx.ConnectError("Connection refused"))
    original_env = os.environ.get("LOGMON_ENV")
    os.environ["LOGMON_ENV"] = "dev"
    try:
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
            "has_code_block": 0
        })
        time_token_questions = [
            "오늘 사용 시간 알려줘",
            "AI 토큰 얼마나 썼어?",
            "사용량 보여줘",
        ]
        for q in time_token_questions:
            prompt = "[과거 로그 컨텍스트]\n\n[사용자 질문]\n" + q + "\n[답변]"
            result = await generate_completion(prompt)
            assert "사용 시간:" in result, f"[시간/토큰 분기] 사용 시간: 없음 - 질문={q}, 응답={result}"
            assert "AI 토큰량:" in result, f"[시간/토큰 분기] AI 토큰량: 없음 - 질문={q}, 응답={result}"
            assert not ("총" in result and "개임" in result), f"[시간/토큰 분기] 에러 개수 응답 오반환 - 질문={q}, 응답={result}"
    finally:
        if original_env is not None:
            os.environ["LOGMON_ENV"] = original_env
        else:
            del os.environ["LOGMON_ENV"]


# 8. 가드레일 인프라 키워드 허용 검증
def test_guardrail_allows_infrastructure_keywords():
    """ollama, sqlite, db, 로그, engine, ai 등 인프라 질문이 차단되지 않는지 검증"""
    assert check_guardrail("ollama는 어떻게 구동되지?") is True
    assert check_guardrail("sqlite 쿼리 결과 확인해줘") is True
    assert check_guardrail("RAG engine 동작 원리") is True
    assert check_guardrail("AI 모델 변경 내역") is True


# 9. Ollama 온라인 시 Fallback 미동작 검증
@pytest.mark.asyncio
@respx.mock
async def test_client_completion_no_fallback_on_online():
    """Ollama 온라인 상태일 때 Fallback이 트리거되지 않고 정상 답변이 리턴되는지 검증"""
    base = OLLAMA_HOST.rstrip("/")
    endpoint = f"{base}/api/generate"
    respx.post(endpoint).mock(return_value=httpx.Response(200, json={"response": "Online Model Response"}))
    original_env = os.environ.get("LOGMON_ENV")
    os.environ["LOGMON_ENV"] = "dev"
    try:
        result = await generate_completion("사용시간 가이드")
        assert "백업 장부(SQLite) 분석 결과" not in result
        assert result == "Online Model Response"
    finally:
        if original_env is not None:
            os.environ["LOGMON_ENV"] = original_env
        else:
            del os.environ["LOGMON_ENV"]


# 10. [NULL 방어] DB 완전 비어있을 때 사용량 Fallback 0값 정상 반환 검증
@pytest.mark.asyncio
@respx.mock
async def test_simulated_empty_db_returns_zero_usage():
    """
    지정 기간에 로그가 전혀 없어 SUM 결과가 NULL인 경우에도
    '사용 시간: 0.0시간, AI 토큰량: 0개'를 TypeError 없이 반환하는지 검증
    """
    base = OLLAMA_HOST.rstrip("/")
    endpoint = f"{base}/api/generate"
    respx.post(endpoint).mock(side_effect=httpx.ConnectError("Connection refused"))
    original_env = os.environ.get("LOGMON_ENV")
    os.environ["LOGMON_ENV"] = "dev"
    try:
        from backend.db.connection import get_connection
        # DB를 완전히 비운다
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ide_activity_logs")
        conn.commit()
        conn.close()

        prompt = "[과거 로그 컨텍스트]\n\n[사용자 질문]\n오늘 사용 시간 알려줘\n[답변]"
        result = await generate_completion(prompt)

        # NULL 반환 시 0값으로 치환된 정상 포맷 검증
        assert "사용 시간:" in result, f"[빈 DB] 사용 시간: 없음, 응답={result}"
        assert "AI 토큰량:" in result, f"[빈 DB] AI 토큰량: 없음, 응답={result}"
        assert "0.0시간" in result, f"[빈 DB] 0.0시간 없음, 응답={result}"
        assert "0개" in result, f"[빈 DB] 0개 없음, 응답={result}"
    finally:
        if original_env is not None:
            os.environ["LOGMON_ENV"] = original_env
        else:
            del os.environ["LOGMON_ENV"]


# 11. [어미 치환 격리] '안녕하세요'·'필요' 보존어 절대 오치환 방지 격리 테스트
def test_postprocess_noun_ending_preserve_words_isolation():
    """
    '안녕하세요', '필요', '보세요' 등 보존어가
    명사형 종결 어미 필터에 의해 절대 오치환되지 않는지 격리 검증
    """
    # 보존어 단독 입력 — 절대 변형 금지
    assert postprocess_noun_ending("안녕하세요.") == "안녕하세요."
    assert postprocess_noun_ending("필요합니다.") == "필요함."        # 합니다 → 함 (정상 치환)
    assert postprocess_noun_ending("안녕하세요. 필요합니다.") == "안녕하세요. 필요함."
    # '안녕요망', '필요망' 등의 오치환이 절대 발생하지 않아야 함
    result1 = postprocess_noun_ending("안녕하세요.")
    assert "요망" not in result1, f"'안녕하세요.' 오치환 발생: {result1}"
    result2 = postprocess_noun_ending("디버깅해 보세요.")
    assert result2 == "디버깅해 보세요.", f"'보세요' 오치환 발생: {result2}"
    result3 = postprocess_noun_ending("확인이 필요합니다.")
    assert "필요요망" not in result3, f"'필요' 오치환 발생: {result3}"


# 12. 타임존 및 중복 누수 교차 검증 테스트
def test_timezone_and_duplicate_leak_cross_validation():
    """타임존 및 중복 누수 방지 로직 교차 검증"""
    from backend.db.sqlite_logs import insert_activity_log, check_duplicate_log
    from backend.db.connection import get_connection
    
    user_key = "TZ_DUP_TEST_USER"
    timestamp = "2026-06-22 15:30:00"
    
    log_data = {
        "user_key": user_key,
        "source_tool": "Cursor",
        "timestamp": timestamp,
        "event_type": "INFO",
        "task_name": "CODING",
        "duration_seconds": 10,
        "input_tokens": 10,
        "output_tokens": 10,
        "raw_message": "Test Message",
        "has_code_block": 0
    }
    
    # 1. 첫 번째 삽입
    first_id = insert_activity_log(log_data)
    assert first_id is not None
    
    # 2. 동일한 타임스탬프로 두 번째 삽입 시도 (중복 스킵되어 None 반환해야 함)
    second_id = insert_activity_log(log_data)
    assert second_id is None
    
    # 3. 중복 확인 함수 자체도 True 반환해야 함
    assert check_duplicate_log(user_key, timestamp) is True
    
    # 4. DB 커넥션이 누수 없이 닫혔는지 확인하기 위해 DB 연결 후 select가 정상 작동하는지 확인
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM ide_activity_logs WHERE user_key = ?", (user_key,))
    count = cursor.fetchone()[0]
    assert count == 1
    conn.close()


