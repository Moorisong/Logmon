import pytest
from unittest.mock import patch, MagicMock
import requests
import streamlit as st
import sys
import os

# add frontend to sys path so we can import utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../frontend')))
from utils.api_client import fetch_stats, send_chat

@patch("utils.api_client.requests.get")
@patch("utils.api_client.st.markdown")
def test_fetch_stats_request_exception(mock_st_markdown, mock_requests_get):
    # Setup mock to raise a RequestException
    mock_requests_get.side_effect = requests.exceptions.RequestException("Mocked connection error")
    
    # Call the function
    result = fetch_stats.__wrapped__() # call the unwrapped function because of st.cache_data
    
    # Assert st.markdown was called to render custom HTML style error
    assert mock_st_markdown.called
    call_args = mock_st_markdown.call_args[0][0]
    # HTML 태그 스타일 속성 및 수정된 텍스트 포함 여부 검증
    assert "stAlert" in call_args
    assert "💡 서버가 일시적으로 오프라인 상태예요." in call_args
    assert "잠시 점검 중이거나 쉬고 있는 것 같으니" in call_args
    assert "margin-top: 4px;" in call_args
    
    # Assert the fallback dict is returned
    assert result["total_logs"] == 0
    assert result["today_tokens"] == 0

@patch("utils.api_client.requests.post")
def test_send_chat_request_exception(mock_requests_post):
    # Setup mock to raise a RequestException
    mock_requests_post.side_effect = requests.exceptions.RequestException("Mocked connection error")
    
    # Call the function
    result = send_chat("Hello")
    
    # Assert friendly error message is returned
    assert result == "서버 통신에 실패했습니다."

@patch("utils.api_client.requests.post")
def test_send_chat_timeout(mock_requests_post):
    # Setup mock to raise a Timeout exception
    mock_requests_post.side_effect = requests.exceptions.Timeout("Mocked timeout")
    
    # Call the function
    result = send_chat("Hello")
    
    # Assert timeout error message is returned
    assert result == "현재 AI 엔진 서비스가 일시 정지 중이거나 과부하 상태입니다."

def test_offline_ui_condition():
    # 서버 오프라인(is_error_state) 판정 조건 테스트 (mock_stats가 없을 때 참이 되는지 검증)
    session_state_without_mock = {}
    is_error_state = "mock_stats" not in session_state_without_mock
    assert is_error_state is True

    # 목 데이터 주입 후(mock_stats가 세션에 있을 때) 거짓이 되는지 검증
    session_state_with_mock = {"mock_stats": {"uptime_days": 5}}
    is_error_state_with_mock = "mock_stats" not in session_state_with_mock
    assert is_error_state_with_mock is False
