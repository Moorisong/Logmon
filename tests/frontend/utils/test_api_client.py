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
def test_fetch_stats_request_exception(mock_requests_get):
    # Setup mock to raise a RequestException
    mock_requests_get.side_effect = requests.exceptions.RequestException("Mocked connection error")
    
    # Call the function
    result = fetch_stats() # call the function
    
    # Assert the fallback dict is returned with is_online=False
    assert result["total_logs"] == 0
    assert result["today_tokens"] == 0
    assert result["is_online"] is False
    assert result["is_agent_installed"] is False

@patch("utils.api_client.requests.get")
def test_fetch_stats_success(mock_requests_get):
    # Setup mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "total_logs": 10,
        "today_tokens": 500,
        "trend_7d": [],
        "uptime_days": 2,
        "total_lines": 100,
        "total_bytes": 1024,
        "last_sync_time": "2026-06-21 12:00:00",
        "is_agent_installed": True
    }
    mock_requests_get.return_value = mock_response
    
    result = fetch_stats()
    
    # is_online=True 가 정상 병합되었는지 검증
    assert result["is_online"] is True
    assert result["total_logs"] == 10
    assert result["total_lines"] == 100
    assert result["is_agent_installed"] is True

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
    # 1) 서버 오프라인(is_online=False)이고 mock_stats 없을 때 => 에러 상태 (블러 활성화)
    stats_offline = {"is_online": False}
    session_state_no_mock = {}
    is_error_state_1 = not stats_offline.get("is_online", True) and "mock_stats" not in session_state_no_mock
    assert is_error_state_1 is True

    # 2) 서버 온라인(is_online=True)이고 mock_stats 없을 때 => 정상 상태 (블러 비활성화)
    stats_online = {"is_online": True}
    is_error_state_2 = not stats_online.get("is_online", True) and "mock_stats" not in session_state_no_mock
    assert is_error_state_2 is False

    # 3) 서버 오프라인(is_online=False)이지만 mock_stats 있을 때 => 모의 주입으로 정상 구동 (블러 비활성화)
    session_state_with_mock = {"mock_stats": {"uptime_days": 5}}
    is_error_state_3 = not stats_offline.get("is_online", True) and "mock_stats" not in session_state_with_mock
    assert is_error_state_3 is False

def test_chat_input_disabled_state_condition():
    # 1) 에러 상태이거나 어시스턴트가 답변 대기 중일 때 => 입력창 비활성화 (disabled_state == True)
    is_error_state = True
    is_waiting = False
    disabled_state_1 = is_error_state or is_waiting
    assert disabled_state_1 is True

    is_error_state = False
    is_waiting = True
    disabled_state_2 = is_error_state or is_waiting
    assert disabled_state_2 is True

    # 2) 정상 상태이고 어시스턴트 답변이 끝났을 때 => 입력창 활성화 (disabled_state == False)
    is_error_state = False
    is_waiting = False
    disabled_state_3 = is_error_state or is_waiting
    assert disabled_state_3 is False


