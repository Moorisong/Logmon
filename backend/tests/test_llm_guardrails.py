# backend/tests/test_llm_guardrails.py
import os
import pytest
import datetime
from unittest.mock import patch

# 테스트 환경 강제 분리
os.environ["LOGMON_ENV"] = "test"
os.environ["LOGMON_DB_DIR"] = "/tmp/logmon_test_llm_guardrails_db"
os.environ["LOGMON_CHROMA_DIR"] = "/tmp/logmon_test_llm_guardrails_chroma"

from backend.db.connection import init_db
from backend.llm.utils import postprocess_noun_ending
from backend.llm.guardrail import check_guardrail
from backend.llm.rag_engine import ask_rag_agent

@pytest.fixture(autouse=True)
def setup_and_teardown():
    init_db()
    yield
    if os.path.exists(os.environ["LOGMON_DB_DIR"]):
        import shutil
        shutil.rmtree(os.environ["LOGMON_DB_DIR"], ignore_errors=True)

def test_postprocess_noun_ending_conversion():
    """1. 여러 문장 어미가 명사형으로 잘 변환되는지 검증"""
    assert postprocess_noun_ending("문제를 확인했습니다.") == "문제를 확인했음."
    assert postprocess_noun_ending("도커 빌드를 시작하겠습니다.") == "도커 빌드를 시작하겠음."
    assert postprocess_noun_ending("정상 조치되었습니다.") == "정상 조치됨."
    assert postprocess_noun_ending("경고 로그를 출력합니다.") == "경고 로그를 출력함."

def test_postprocess_noun_ending_avoid_over_replace():
    """2. '요망', '요청' 등에서 '요'가 공백으로 잘못 지워지지 않는지 검증"""
    # '요.?' 가 맨 뒤에만 매칭되도록 설계했으므로, 중간의 '요망', '요청' 등의 요는 보존되어야 함
    assert postprocess_noun_ending("조치가 필요요망.") == "조치가 필요요망."
    assert postprocess_noun_ending("수정을 요청합니다.") == "수정을 요청함."

def test_guardrail_fuzzy_matching_spaces():
    """3. 띄어쓰기가 완전히 파괴된 질문이 가드레일을 무사히 통과하는지 검증"""
    assert check_guardrail("최근에발생한도커포트오류") is True
    assert check_guardrail("에러로그확인해줘") is True

def test_guardrail_fuzzy_matching_typos():
    """4. 모음 오타 질문이 가드레일을 무사히 통과하는지 검증"""
    assert check_guardrail("디비 커낵션 에러") is True
    assert check_guardrail("경고로드") is True
    assert check_guardrail("에러 로드") is True

def test_guardrail_blocking_non_tech():
    """5. 완전한 일상 질의 입력 시 변경된 도메인 거부 메시지 필터 작동 검증"""
    assert check_guardrail("오늘 날씨 어때") is False
    assert check_guardrail("비트코인 시세 조회") is False
    assert check_guardrail("치킨 추천해줘") is False

@pytest.mark.asyncio
@patch('backend.llm.rag_engine.query_vectors')
@patch('backend.llm.rag_engine.generate_completion')
@patch('backend.llm.rag_engine.rerank_documents')
@patch('backend.llm.rag_engine.logger.warning')
async def test_rag_token_ceiling_and_dropping_guardrails(mock_warn, mock_rerank, mock_generate, mock_query):
    """6. 1,800 토큰 초과 시 청크를 드롭하고 [WARN] 로그를 기록하는지 검증"""
    large_chunk = "A" * 2500  # 약 1000 토큰
    mock_query.return_value = [[
        f"[2026-06-22 10:00:00] {large_chunk}",
        f"[2026-06-22 10:05:00] {large_chunk}",
        f"[2026-06-22 10:10:00] {large_chunk}"
    ]]
    mock_rerank.side_effect = lambda query, documents, top_k, max_chars: "\n".join(documents)
    mock_generate.return_value = "처리 완료했습니다."
    
    answer = await ask_rag_agent("경고로그 분석해줘", "test_user_key")
    
    # 1800 초과로 드롭되어 warning이 기록되고
    assert mock_warn.called
    any_warn_call = any("[WARN] Token limit exceeded. Dropping oldest chunk..." in call[0][0] for call in mock_warn.call_args_list)
    assert any_warn_call
    # 어미 후처리가 되어 명사형으로 출력되었는지 검증
    assert answer == "처리 완료함."

@pytest.mark.asyncio
@patch('backend.llm.rag_engine.query_vectors')
@patch('backend.llm.rag_engine.generate_completion')
@patch('backend.llm.rag_engine.rerank_documents')
@patch('backend.llm.rag_engine.logger.warning')
async def test_rag_token_ceiling_no_drop(mock_warn, mock_rerank, mock_generate, mock_query):
    """7. 1,800 토큰 이하일 때는 드롭 없이 전체 컨텍스트가 유지되는지 검증"""
    small_chunk = "A" * 100  # 아주 작은 크기
    mock_query.return_value = [[
        f"[2026-06-22 10:00:00] {small_chunk}",
    ]]
    mock_rerank.side_effect = lambda query, documents, top_k, max_chars: "\n".join(documents)
    mock_generate.return_value = "처리 완료함"
    
    await ask_rag_agent("에러 검색해줘", "test_user_key")
    
    # 드롭 경고가 호출되지 않아야 함
    assert not mock_warn.called

@pytest.mark.asyncio
async def test_rag_empty_context_handling_guardrails():
    """8. 컨텍스트가 전혀 없을 때 LLM 호출 없이 방어 문구를 반환하는지 검증"""
    with patch('backend.llm.rag_engine.query_vectors', return_value=[]):
        with patch('backend.llm.rag_engine.generate_completion') as mock_llm:
            answer = await ask_rag_agent("에러 찾아줘", "test_key")
            assert answer == "최근 기록된 작업 로그가 존재하지 않습니다."
            mock_llm.assert_not_called()

@pytest.mark.asyncio
@patch('backend.llm.rag_engine.query_vectors')
@patch('backend.llm.rag_engine.generate_completion')
async def test_rag_date_filtering_today(mock_generate, mock_query):
    """9. 질문에 '오늘' 의도가 포함될 때 당일 로그 외의 과거 로그가 정확히 필터링되어 제외되는지 검증 (날짜 혼동 방지)"""
    import datetime
    timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
    today_str = datetime.datetime.now(timezone_kst).strftime('%Y-%m-%d')
    
    mock_query.return_value = [[
        f"[{today_str} 10:00:00] [ERROR] Docker binding error",
        "[2026-05-03 14:00:00] [ERROR] Connection lost error"
    ]]
    mock_generate.return_value = "오늘 에러 분석 완료함"
    
    answer = await ask_rag_agent("오늘 발생한 에러 분석해줘", "test_user_key")
    
    # 생성된 프롬프트에 오늘 날짜 로그만 들어가고 과거 로그는 드롭되어야 함
    prompt_sent = mock_generate.call_args[0][0]
    assert f"[{today_str} 10:00:00]" in prompt_sent
    assert "[2026-05-03 14:00:00]" not in prompt_sent

@pytest.mark.asyncio
@patch('backend.llm.rag_engine.query_vectors')
@patch('backend.llm.rag_engine.generate_completion')
@patch('backend.llm.rag_engine.logger.info')
async def test_rag_date_filtering_parsed_range(mock_info, mock_generate, mock_query):
    """10. 시간 맥락 파싱 범위와 필터링 후 남은 청크 개수가 콘솔 로그에 기록되는지 검증 (지침 B)"""
    mock_query.return_value = [["[2026-06-22 10:00:00] [ERROR] Docker binding error"]]
    mock_generate.return_value = "처리 완료함"
    
    await ask_rag_agent("어제 발생한 에러 분석해줘", "test_user_key")
    
    # 시간 맥락 파싱 로그 기록 확인
    assert mock_info.called
    any_parse_call = any("[시간 맥락 파싱]" in call[0][0] for call in mock_info.call_args_list)
    assert any_parse_call
    any_post_filter_call = any("[날짜 후처리 필터 결과]" in call[0][0] for call in mock_info.call_args_list)
    assert any_post_filter_call

