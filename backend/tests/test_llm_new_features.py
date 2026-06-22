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

@pytest.fixture(autouse=True)
def setup_and_teardown():
    from backend.llm.memory import _conversation_memory
    _conversation_memory.clear()
    init_db()
    yield
    _conversation_memory.clear()
    if os.path.exists(os.environ["LOGMON_DB_DIR"]):
        shutil.rmtree(os.environ["LOGMON_DB_DIR"], ignore_errors=True)

# 1. 상대 기간 날짜 파서 단위 테스트 3종
def test_parse_relative_datetime_past_two_days():
    """'지난 2일 동안' 질문 입력 시 KST 기준 정상 파싱 여부 검증"""
    start_time, end_time = parse_relative_datetime("지난 2일 동안 발생한 에러 보여줘")
    assert start_time is not None
    assert end_time is not None
    assert start_time.endswith("00:00:00")
    
    start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    delta = end_dt - start_dt
    assert 1.9 <= delta.days <= 2.1

def test_parse_relative_datetime_one_week():
    """'일주일 동안' 질문 입력 시 KST 기준 정상 파싱 여부 검증"""
    start_time, end_time = parse_relative_datetime("일주일 동안의 빌드 로그 요약해줘")
    assert start_time is not None
    assert end_time is not None
    assert start_time.endswith("00:00:00")
    
    start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    delta = end_dt - start_dt
    assert 6.9 <= delta.days <= 7.1

def test_parse_relative_datetime_fallback():
    """매칭되지 않는 일반 질문 입력 시 None 반환 및 예외 안전망 작동 검증"""
    start_time, end_time = parse_relative_datetime("그냥 일반적인 기술 질문")
    assert start_time is None
    assert end_time is None

# 2. 타겟 모델이 llama3.2:1b 인지 검증하는 Mock 테스트
@pytest.mark.asyncio
@respx.mock
async def test_llm_client_uses_llama_model():
    """Ollama API 호출 시 모델 이름이 llama3.2:1b로 설정되어 전송되는지 검증"""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    
    mock_route = respx.post(endpoint).mock(
        return_value=httpx.Response(200, json={"response": "Llama Answer"})
    )
    
    assert MODEL_NAME == "llama3.2:1b"
    
    result = await generate_completion("테스트용 프롬프트")
    assert result == "Llama Answer"
    
    request = mock_route.calls.last.request
    import json
    payload = json.loads(request.content)
    assert payload["model"] == "llama3.2:1b"

# 3. 동적 컨텍스트 압축(Truncate) 동작 검증 테스트
def test_manage_context_token_limit_truncation():
    """매우 긴 컨텍스트 주입 시 청크 개수를 유지하되 문자열 길이를 줄여 1,800 토큰 이하로 압축하는지 검증"""
    docs = [
        "RawMessage: " + ("a" * 2000),
        "RawMessage: " + ("b" * 2000),
        "RawMessage: " + ("c" * 2000)
    ]
    question = "전체 로그 요약"
    final_question = "전체 로그 요약"
    current_date_str = "2026-06-22"
    
    context_str = manage_context_token_limit(
        docs=docs,
        question=question,
        final_question=final_question,
        selected_template=COUNT_PROMPT_TEMPLATE,
        current_date_str=current_date_str
    )
    
    assert "a" in context_str
    assert "b" in context_str
    assert "c" in context_str
    
    prompt = COUNT_PROMPT_TEMPLATE.format(
        current_date=current_date_str,
        context=context_str,
        question=final_question
    )
    from backend.llm.utils import estimate_tokens
    approx_tokens = estimate_tokens(prompt)
    assert approx_tokens <= 1800

# 4. [STATISTICS] 청크 누락 및 파싱 오류 시의 방어 동작 검증
@pytest.mark.asyncio
@patch('backend.llm.rag_engine.query_vectors')
@patch('backend.llm.rag_engine.generate_completion')
async def test_ask_rag_agent_statistics_none_fallback(mock_generate, mock_query):
    """STATISTICS 정보가 없는 로그 컨텍스트 수신 시 에러 없이 예외 처리를 거쳐 정상 진행되는지 검증"""
    mock_query.return_value = [[
        "[2026-06-22 10:00:00] [ERROR] DB query connection timeout error"
    ]]
    mock_generate.return_value = "통계 처리 응답 성공"
    
    answer = await ask_rag_agent("오늘 에러 몇 개 발생했어?", "test_user")
    assert answer == "통계 처리 응답 성공"
    
    prompt_sent = mock_generate.call_args[0][0]
    assert "[Calculated Statistics]" not in prompt_sent

# 5. 어미 치환 규칙 및 인사말/필요 명사 오치환 방지 검증 테스트
def test_postprocess_noun_ending_advanced_safety():
    """안녕하세요 및 필요, 보세요 등 보존어가 안녕요망 등으로 훼손되지 않고 보존되는지 검증"""
    assert postprocess_noun_ending("안녕하세요. 반가워요.") == "안녕하세요. 반가워."
    assert postprocess_noun_ending("작업이 필요요망.") == "작업이 필요요망."
    assert postprocess_noun_ending("디버깅해 보세요.") == "디버깅해 보세요."
    assert postprocess_noun_ending("데이터가 필요합니다.") == "데이터가 필요함."

# 6. Ollama 오프라인 상황에서 SQLite 실제 STATISTICS 데이터 포매팅 검증 테스트
@pytest.mark.asyncio
@respx.mock
async def test_client_simulated_response_stats_binding():
    """Ollama 오프라인 모킹(Mocking) 상태에서 SQLite 실제 적재 통계값이 정상적으로 포매팅되어 반환되는지 검증"""
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    respx.post(endpoint).mock(side_effect=httpx.ConnectError("Connection refused"))
    
    # LOGMON_ENV가 test가 아닐 때만 Simulated Response가 동작하므로 강제 설정
    original_env = os.environ.get("LOGMON_ENV")
    os.environ["LOGMON_ENV"] = "dev"
    
    try:
        from backend.db.sqlite_handler import insert_activity_log
        from backend.db.connection import get_connection
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ide_activity_logs WHERE task_name = 'STATISTICS'")
        conn.commit()
        conn.close()
        
        stat_message = """[STATISTICS] [DATE: 2026-06-22]
- Total_Usage_Time: 3.5 Hours
- Total_AI_Tokens_Used: 12500 Tokens
- Total_Log_Count: 15 Cases (INFO: 10, WARN: 3, ERROR: 2)
- Top_Error_Types: [DBError: 2]
- First_Launch_Time: 09:30:00"""
        
        insert_activity_log({
            "user_key": "dev_test",
            "source_tool": "SYSTEM",
            "timestamp": "2026-06-22 10:00:00",
            "event_type": "INFO",
            "task_name": "STATISTICS",
            "duration_seconds": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "raw_message": stat_message,
            "has_code_block": 0
        })
        
        prompt = "[과거 로그 컨텍스트]\n\n[사용자 질문]\n오늘 통계 보여줘\n[답변]"
        result = await generate_completion(prompt)
        
        assert "백업 장부(SQLite) 분석 결과" in result
        assert "당일(2026-06-22) 누적 통계는 사용 시간: 3.5시간" in result
        assert "AI 토큰량: 12500개" in result
    finally:
        if original_env is not None:
            os.environ["LOGMON_ENV"] = original_env
        else:
            del os.environ["LOGMON_ENV"]
