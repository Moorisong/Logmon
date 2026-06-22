# backend/tests/test_llm_new_features.py
import pytest
import datetime
import respx
import httpx
from unittest.mock import patch

from backend.llm.utils import parse_relative_datetime, manage_context_token_limit
from backend.llm.client import generate_completion, OLLAMA_HOST, MODEL_NAME
from backend.llm.rag_engine import ask_rag_agent
from backend.llm.prompt_templates import COUNT_PROMPT_TEMPLATE

# 1. 상대 기간 날짜 파서 단위 테스트 3종
def test_parse_relative_datetime_past_two_days():
    """'지난 2일 동안' 질문 입력 시 KST 기준 정상 파싱 여부 검증"""
    start_time, end_time = parse_relative_datetime("지난 2일 동안 발생한 에러 보여줘")
    assert start_time is not None
    assert end_time is not None
    
    # 00:00:00 포맷 및 일수 차이 확인
    assert start_time.endswith("00:00:00")
    start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    delta = end_dt - start_dt
    assert 1.9 <= delta.days <= 2.1  # 대략 2일 차이

def test_parse_relative_datetime_one_week():
    """'일주일 동안' 질문 입력 시 KST 기준 정상 파싱 여부 검증"""
    start_time, end_time = parse_relative_datetime("일주일 동안의 빌드 로그 요약해줘")
    assert start_time is not None
    assert end_time is not None
    assert start_time.endswith("00:00:00")
    
    start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    delta = end_dt - start_dt
    assert 6.9 <= delta.days <= 7.1  # 대략 7일 차이

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
    
    # 모델명 변수 체크
    assert MODEL_NAME == "llama3.2:1b"
    
    result = await generate_completion("테스트용 프롬프트")
    assert result == "Llama Answer"
    
    # 요청 페이로드 모델 검증
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
    # 총 토큰 수가 1,800(약 4500자)을 훌쩍 넘어가도록 설정
    question = "전체 로그 요약"
    final_question = "전체 로그 요약"
    current_date_str = "2026-06-22"
    
    # context 압축 수행
    context_str = manage_context_token_limit(
        docs=docs,
        question=question,
        final_question=final_question,
        selected_template=COUNT_PROMPT_TEMPLATE,
        current_date_str=current_date_str
    )
    
    # 3개 청크가 드롭되지 않고 모두 텍스트 내부에 포함되어 있어야 함
    assert "a" in context_str
    assert "b" in context_str
    assert "c" in context_str
    
    # 전체 프롬프트 토큰 예측값 확인
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
    # STATISTICS 문자열이 없는 일반 에러 청크 제공
    mock_query.return_value = [[
        "[2026-06-22 10:00:00] [ERROR] DB query connection timeout error"
    ]]
    mock_generate.return_value = "통계 처리 응답 성공"
    
    # 에러 개수를 묻는 count 질의 수행 (is_count_query가 True로 잡히게 설정)
    answer = await ask_rag_agent("오늘 에러 몇 개 발생했어?", "test_user")
    
    # 크래시 없이 응답이 성공적으로 수행되어야 함
    assert answer == "통계 처리 응답 성공"
    
    # 프롬프트 인풋 확인
    prompt_sent = mock_generate.call_args[0][0]
    # match 실패 시 기본값 세팅을 통해 [Calculated Statistics]가 삽입되지 않고 무사통과하거나 방어되어야 함
    assert "[Calculated Statistics]" not in prompt_sent
