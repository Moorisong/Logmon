import pytest
from unittest.mock import patch, MagicMock
import requests
import streamlit as st
import sys
import os

# add frontend to sys path so we can import utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../frontend')))
from utils.api_client import fetch_stats

@patch("utils.api_client.requests.get")
@patch("utils.api_client.st.error")
def test_fetch_stats_request_exception(mock_st_error, mock_requests_get):
    # Setup mock to raise a RequestException
    mock_requests_get.side_effect = requests.exceptions.RequestException("Mocked connection error")
    
    # Call the function
    result = fetch_stats.__wrapped__() # call the unwrapped function because of st.cache_data
    
    # Assert st.error was called with the updated friendly message
    mock_st_error.assert_called_once_with("통계 데이터를 불러올 수 없습니다. 서버 상태를 확인해주세요.")
    
    # Assert the fallback dict is returned
    assert result["total_logs"] == 0
    assert result["today_tokens"] == 0
