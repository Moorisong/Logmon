import os
import pytest
import respx
import httpx
from unittest.mock import patch

# --- 테스트 환경 강제 분리 ---
os.environ["LOGMON_ENV"] = "test"
os.environ["LOGMON_DB_DIR"] = "/tmp/logmon_test_llm_db"
os.environ["LOGMON_CHROMA_DIR"] = "/tmp/logmon_test_llm_chroma"

from backend.db.connection import init_db, get_connection
from backend.llm.client import generate_completion, OLLAMA_HOST, OLLAMA_NUM_THREAD
from backend.llm.rag_engine import ask_rag_agent
from backend.llm.prompt_templates import ERROR_FALLBACK_MESSAGE

@pytest.fixture(autouse=True)
def setup_and_teardown():
    init_db()
    yield
    if os.path.exists(os.environ["LOGMON_DB_DIR"]):
        import shutil
        shutil.rmtree(os.environ["LOGMON_DB_DIR"], ignore_errors=True)

# 1. 비동기 HTTP 클라이언트 Mock 테스트 (respx 활용)
@pytest.mark.asyncio
@respx.mock
async def test_llm_client_success():
    """정상적으로 Ollama API가 응답할 때의 결과 파싱 테스트"""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    
    mock_route = respx.post(endpoint).mock(
        return_value=httpx.Response(200, json={"response": "Mocked AI Answer"})
    )
    
    result = await generate_completion("테스트 질문")
    
    assert mock_route.called
    assert result == "Mocked AI Answer"
    
    # Payload에 num_thread가 잘 들어갔는지 확인
    request = mock_route.calls.last.request
    import json
    payload = json.loads(request.content)
    assert payload["options"]["num_thread"] == OLLAMA_NUM_THREAD

@pytest.mark.asyncio
@respx.mock
async def test_llm_client_timeout_fallback():
    """타임아웃 발생 시 안전 장치 메시지가 반환되는지 테스트"""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    
    respx.post(endpoint).mock(side_effect=httpx.TimeoutException("Timeout"))
    
    result = await generate_completion("지연되는 질문")
    assert result == ERROR_FALLBACK_MESSAGE

@pytest.mark.asyncio
@respx.mock
async def test_llm_client_connection_error_fallback():
    """서버 다운 등 Network Error 발생 시 안전 장치 반환 테스트"""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    
    respx.post(endpoint).mock(side_effect=httpx.ConnectError("Connection refused"))
    
    result = await generate_completion("서버 다운 질문")
    assert result == ERROR_FALLBACK_MESSAGE

@pytest.mark.asyncio
@patch('backend.llm.rag_engine.query_vectors')
@patch('backend.llm.rag_engine.generate_completion')
async def test_ask_rag_agent_with_context(mock_generate, mock_query):
    # Chroma DB에서 유사 문서를 찾아왔다고 가정
    mock_query.return_value = [["과거 로그 내용 1", "과거 로그 내용 2"]]
    mock_generate.return_value = "RAG 처리된 AI 응답"
    
    answer = await ask_rag_agent("도커 에러 어떻게 풀었지?", "test_user_key")
    
    assert answer == "RAG 처리된 AI 응답"
    mock_query.assert_called_once_with(
        query_text="도커 에러 어떻게 풀었지?",
        n_results=10,
        user_key="test_user_key",
        event_type="ERROR",
        start_time=None,
        end_time=None,
        keywords=['error', 'error', '에러', '오류', '실패', 'fail']
    )

    
    # 생성된 프롬프트 검증
    prompt_sent = mock_generate.call_args[0][0]
    assert "과거 로그 내용 1" in prompt_sent
    assert "도커 에러 어떻게 풀었지?" in prompt_sent
    
    # KST 오늘 날짜가 프롬프트에 동적 주입되었는지 확인
    import datetime
    timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
    today_str = datetime.datetime.now(timezone_kst).strftime('%Y-%m-%d')
    assert f"Current Server Time (KST): {today_str}" in prompt_sent

@pytest.mark.asyncio
@respx.mock
async def test_llm_client_connection_error_dynamic_mock_fallback():
    """서버 다운 상황에서 LOGMON_ENV가 test가 아닐 때 실제 SQLite 로그를 이용한 동적 모의 답변 생성 테스트"""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    
    respx.post(endpoint).mock(side_effect=httpx.ConnectError("Connection refused"))
    
    # 임시로 LOGMON_ENV를 dev로 바꿨다가 원복
    original_env = os.environ.get("LOGMON_ENV")
    os.environ["LOGMON_ENV"] = "dev"
    
    try:
        from backend.db.sqlite_handler import insert_activity_log
        mock_log = {
            "user_key": "dev",  # LOGMON_ENV가 dev이고 API Key 검증을 직접 하지 않는 경로이므로 매핑될 수 있는 값이나 일반 문자열
            "timestamp": "2026-06-21 12:00:00",
            "source_tool": "VSCode",
            "event_type": "ERROR",
            "task_name": "Build",
            "duration_seconds": 10,
            "input_tokens": 100,
            "output_tokens": 50,
            "raw_message": "Exception: Connection refused in db.py",
            "has_code_block": 0
        }
        insert_activity_log(mock_log)

        # DB 세팅을 모의하기 위해 context와 question이 포함된 프롬프트 작성
        prompt = """당신은 어시스턴트입니다.
[과거 로그 컨텍스트]
관련된 과거 로그 컨텍스트가 없습니다.

[사용자 질문]
오늘 무슨 에러 있었어?

[답변]"""
        result = await generate_completion(prompt)
        
        # 동적 모의 응답이 생성되었는지 확인
        assert "안녕하세요!" in result
        assert "실제 저장된 로그 데이터" in result
        assert "오늘" in result or "과거" in result
    finally:
        if original_env is not None:
            os.environ["LOGMON_ENV"] = original_env
        else:
            del os.environ["LOGMON_ENV"]

@pytest.mark.asyncio
@respx.mock
async def test_llm_client_timeout_dynamic_mock_fallback():
    """타임아웃 에러 상황에서 SQLite 로직으로 누수 없이 흐르는지 검증 (Bug Fix Test)"""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    respx.post(endpoint).mock(side_effect=httpx.TimeoutException("Timeout"))
    
    original_env = os.environ.get("LOGMON_ENV")
    os.environ["LOGMON_ENV"] = "dev"
    try:
        from backend.db.sqlite_handler import insert_activity_log
        insert_activity_log({"user_key": "dev", "timestamp": "2026-06-21 12:00:00", "source_tool": "VSCode", "event_type": "ERROR", "raw_message": "Timeout trigger"})
        
        prompt = "[과거 로그 컨텍스트]\n\n[사용자 질문]\n오늘 무슨 일?\n[답변]"
        result = await generate_completion(prompt)
        assert "안녕하세요!" in result
        assert "실제 저장된 로그 데이터" in result
    finally:
        if original_env is not None: os.environ["LOGMON_ENV"] = original_env
        else: del os.environ["LOGMON_ENV"]

@pytest.mark.asyncio
@respx.mock
async def test_llm_client_general_exception_dynamic_mock_fallback():
    """알 수 없는 에러 상황에서 SQLite 로직으로 누수 없이 흐르는지 검증 (Bug Fix Test)"""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    respx.post(endpoint).mock(side_effect=Exception("Unknown Error"))
    
    original_env = os.environ.get("LOGMON_ENV")
    os.environ["LOGMON_ENV"] = "dev"
    try:
        prompt = "[과거 로그 컨텍스트]\n\n[사용자 질문]\n알 수 없는 에러\n[답변]"
        result = await generate_completion(prompt)
        assert "안녕하세요!" in result
    finally:
        if original_env is not None: os.environ["LOGMON_ENV"] = original_env
        else: del os.environ["LOGMON_ENV"]

@pytest.mark.asyncio
async def test_guardrail_routing():
    """인풋 가드레일 라우팅 테스트 (비정상 입력 차단)"""
    from backend.llm.guardrail import check_guardrail
    assert check_guardrail("안녕") is False
    assert check_guardrail("너 바보야?") is False
    assert check_guardrail("도커 에러가 왜 나지?") is True
    assert check_guardrail("ide 실행 시간은 어떻게 돼?") is True
    assert check_guardrail("ai 토큰량 질문") is True
    assert check_guardrail("경고 로드 확인해줘") is True  # Fuzzy matching (로그 -> 로드)


@pytest.mark.asyncio
async def test_ask_rag_agent_guardrail_fallback():
    """비기술적 질문 입력 시 변경된 가드레일 멘트가 나오는지 검증"""
    from backend.llm.rag_engine import ask_rag_agent
    from backend.llm.guardrail import GUARDRAIL_FALLBACK_MSG
    
    answer = await ask_rag_agent("오늘 저녁 메뉴 추천해줘", "test_key")
    assert answer == GUARDRAIL_FALLBACK_MSG

@pytest.mark.asyncio
@patch('backend.llm.rag_engine.query_vectors')
@patch('backend.llm.rag_engine.generate_completion')
async def test_ask_rag_agent_today_date_filtering(mock_generate, mock_query):
    """과거 날짜 로그가 오늘 날짜 필터링에 의해 올바르게 걸러지는지 검증"""
    import datetime
    timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
    today_str = datetime.datetime.now(timezone_kst).strftime('%Y-%m-%d')
    
    # Chroma DB에서 오늘 로그와 과거 로그가 함께 섞여서 반환되었다고 가정
    mock_query.return_value = [[
        f"[{today_str} 10:00:00] [ERROR] Docker binding error",
        "[2026-05-03 14:00:00] [ERROR] Connection lost error"
    ]]
    mock_generate.return_value = "오늘 에러 분석 완료"
    
    answer = await ask_rag_agent("오늘 발생한 에러 분석해줘", "test_user_key")
    
    assert answer == "오늘 에러 분석 완료"
    # 생성된 프롬프트 검증 - 오늘 날짜 로그는 프롬프트에 들어가고, 과거 로그는 파이썬 단에서 Drop 되어 없어야 함
    prompt_sent = mock_generate.call_args[0][0]
    assert f"[{today_str} 10:00:00] [ERROR] Docker binding error" in prompt_sent
    assert "[2026-05-03 14:00:00]" not in prompt_sent

@pytest.mark.asyncio
async def test_rag_empty_context_handling():
    """Empty Context 발생 시 LLM을 호출하지 않고 방어하는지 검증"""
    from backend.llm.rag_engine import ask_rag_agent
    with patch('backend.llm.rag_engine.query_vectors', return_value=[]):
        with patch('backend.llm.rag_engine.generate_completion') as mock_llm:
            answer = await ask_rag_agent("에러 찾아줘", "test_key")
            assert answer == "최근 기록된 작업 로그가 존재하지 않습니다."
            mock_llm.assert_not_called()

def test_estimate_tokens():
    """글자 수 기반 토큰 수 예측 헬퍼 검증"""
    from backend.llm.utils import estimate_tokens
    assert estimate_tokens("hello") == 5 / 2.5
    assert estimate_tokens("") == 0.0

def test_postprocess_noun_ending():
    """출력 가드레일 (Post-processing) 종결 어미 교정 검증"""
    from backend.llm.utils import postprocess_noun_ending
    assert postprocess_noun_ending("문제가 발생하였습니다.") == "문제가 발생함."
    assert postprocess_noun_ending("설정을 완료했습니다.") == "설정을 완료함."
    assert postprocess_noun_ending("확인해주세요") == "확인요망."
    assert postprocess_noun_ending("서버가 중단되었습니다.") == "서버가 중단됨."

@pytest.mark.asyncio
@patch('backend.llm.rag_engine.query_vectors')
@patch('backend.llm.rag_engine.generate_completion')
async def test_ask_rag_agent_hard_ceiling_drop(mock_generate, mock_query):
    """Hard Ceiling (1,800 토큰 초과 시 오래된 청크 드롭) 규칙 검증"""
    # 3개의 긴 문서 반환 (각 2000글자씩)
    long_doc_1 = "[2026-06-20 09:00:00] [ERROR] " + ("a" * 2000)
    long_doc_2 = "[2026-06-21 10:00:00] [ERROR] " + ("b" * 2000)
    long_doc_3 = "[2026-06-22 11:00:00] [ERROR] " + ("c" * 2000)
    
    mock_query.return_value = [[long_doc_1, long_doc_2, long_doc_3]]
    mock_generate.return_value = "처리 완료됨."
    
    # 1,800 토큰(약 4500자)을 넘기기 위해 매우 긴 사용자 질문 입력
    long_question = "도커 에러 해결법? " + ("q" * 4000)
    
    # RAG 질의 수행
    with patch('backend.llm.rag_engine.logger') as mock_logger:
        answer = await ask_rag_agent(long_question, "test_user_key")
        
        # 1800 토큰 초과로 인해 [WARN] 로그가 최소 1회 발생해야 함
        warn_called = False
        for args, kwargs in mock_logger.warning.call_args_list:
            if args and "[WARN] Token limit exceeded. Dropping oldest chunk..." in args[0]:
                warn_called = True
                break
        assert warn_called
        
    assert answer == "처리 완료됨."

def test_parse_query_filters_today():
    """사용자 질문에 '오늘', 'today', '투데이' 등이 포함되었을 때 오늘 날짜 범위를 올바르게 식별하여 파싱하는지 검증"""
    from backend.llm.rag_engine import parse_query_filters
    import datetime
    
    timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
    today_str = datetime.datetime.now(timezone_kst).strftime('%Y-%m-%d')
    expected_start = f"{today_str} 00:00:00"
    expected_end = f"{today_str} 23:59:59"
    
    # '오늘' 입력 시
    start_time, end_time, event_type, keywords = parse_query_filters("오늘 에러 있었어?")
    assert start_time == expected_start
    assert end_time == expected_end

    # 'today' 입력 시
    start_time, end_time, event_type, keywords = parse_query_filters("Show me today's build logs")
    assert start_time == expected_start
    assert end_time == expected_end



