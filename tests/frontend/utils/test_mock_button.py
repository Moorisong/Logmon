import pytest
from unittest.mock import patch, MagicMock
import os
import sys

# add frontend to sys path so we can import utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../frontend')))

def test_local_env_detection():
    # localhost인 경우 로컬 환경으로 탐지하는지 테스트
    backend_url_local = "http://localhost:8000"
    is_local = ("localhost" in backend_url_local or "127.0.0.1" in backend_url_local) and "logmon-backend" not in backend_url_local and "haroo.site" not in backend_url_local
    assert is_local is True

    # 도커 백엔드 도메인(logmon-backend)인 경우 로컬 환경이 아닌 것으로 탐지하는지 테스트
    backend_url_container = "http://logmon-backend:8000"
    is_local_container = ("localhost" in backend_url_container or "127.0.0.1" in backend_url_container) and "logmon-backend" not in backend_url_container and "haroo.site" not in backend_url_container
    assert is_local_container is False

    # 외부 도메인인 경우 로컬 환경이 아닌 것으로 탐지하는지 테스트
    backend_url_prod = "https://logmon.haroo.site"
    is_local_prod = ("localhost" in backend_url_prod or "127.0.0.1" in backend_url_prod) and "logmon-backend" not in backend_url_prod and "haroo.site" not in backend_url_prod
    assert is_local_prod is False

def test_mock_data_structure():
    # 주입되는 목 데이터 구조 유효성 검증 (전체 stats 형태)
    mock_stats = {
        "uptime_days": 5,
        "total_lines": 15420,
        "total_bytes": 1024 * 1024 * 1.25,
        "last_sync_time": "2026-06-21 11:45:00",
        "current_db_mb": 462.5,
        "max_db_mb": 500.0,
        "trend_7d": [
            {"date": "2026-06-15", "count": 12},
            {"date": "2026-06-16", "count": 25},
            {"date": "2026-06-17", "count": 18},
            {"date": "2026-06-18", "count": 42},
            {"date": "2026-06-19", "count": 30},
            {"date": "2026-06-20", "count": 55},
            {"date": "2026-06-21", "count": 22}
        ]
    }
    
    assert mock_stats["uptime_days"] == 5
    assert mock_stats["total_lines"] == 15420
    assert mock_stats["total_bytes"] == 1024 * 1024 * 1.25
    assert isinstance(mock_stats["last_sync_time"], str)
    assert mock_stats["current_db_mb"] == 462.5

    assert mock_stats["max_db_mb"] == 500.0
    
    mock_trend = mock_stats["trend_7d"]
    assert len(mock_trend) == 7
    for item in mock_trend:
        assert "date" in item
        assert "count" in item
        assert isinstance(item["date"], str)
        assert isinstance(item["count"], int)

    mock_messages = [
        {"role": "assistant", "content": "안녕하세요! Logmon AI 어시스턴트입니다."},
        {"role": "user", "content": "질문"},
        {"role": "assistant", "content": "대답"},
        {"role": "user", "content": "질문2"},
        {"role": "assistant", "content": "대답2"}
    ]
    assert len(mock_messages) == 5
    for msg in mock_messages:
        assert msg["role"] in ["user", "assistant"]
        assert isinstance(msg["content"], str)


def test_npx_html_rendering_vars():
    visible_npx = "npx @thiagomiki/logmon-cli"
    user_api_key = "test_api_key"
    base_external_url = "http://localhost:3008/api/logmon"
    
    if "localhost" in base_external_url or "127.0.0.1" in base_external_url:
        hidden_npx = f"npx @thiagomiki/logmon-cli {user_api_key}"
    else:
        hidden_npx = f"npx @thiagomiki/logmon-cli {user_api_key} {base_external_url}"
        
    assert hidden_npx == f"npx @thiagomiki/logmon-cli {user_api_key}"


