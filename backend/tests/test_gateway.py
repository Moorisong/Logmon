import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.dependencies import get_allowed_api_keys

client = TestClient(app)

# 1. 정적 파일 접근 검증
def test_static_file_serving(tmp_path):
    # static 디렉터리에 더미 파일 생성
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    os.makedirs(static_dir, exist_ok=True)
    
    test_file_path = os.path.join(static_dir, "test.txt")
    with open(test_file_path, "w") as f:
        f.write("dummy content")
        
    response = client.get("/api/logmon/static/test.txt")
    assert response.status_code == 200
    assert response.text == "dummy content"
    
    # 청소
    os.remove(test_file_path)

# 2. API Key 인증 테스트 (401 방어)
@patch.dict(os.environ, {"ALLOWED_API_KEYS": "test_key_1,test_key_2"}, clear=True)
def test_api_key_auth():
    # 헤더 누락
    res_no_header = client.post("/api/logmon/upload", json={
        "source_tool": "Cursor", "event_type": "TEST", "raw_message": "Hello"
    })
    assert res_no_header.status_code == 422 # FastAPI 내장 Header 검증 실패 시 422 발생 (파라미터 누락)
    
    # 잘못된 헤더
    res_invalid = client.post("/api/logmon/upload", json={
        "source_tool": "Cursor", "event_type": "TEST", "raw_message": "Hello"
    }, headers={"X-LogMon-API-Key": "wrong_key"})
    assert res_invalid.status_code == 401
    
    # 설정 누락된 경우 서버 401
    with patch.dict(os.environ, {"ALLOWED_API_KEYS": ""}, clear=True):
        res_no_config = client.post("/api/logmon/upload", json={
            "source_tool": "Cursor", "event_type": "TEST", "raw_message": "Hello"
        }, headers={"X-LogMon-API-Key": "test_key_1"})
        assert res_no_config.status_code == 401

# 3. 페이로드 손상 및 파이프라인 목업 검증 (200 OK)
@patch('backend.api.routes.insert_activity_log')
@patch('backend.api.routes.process_and_store_vector')
@patch.dict(os.environ, {"ALLOWED_API_KEYS": "valid_key"}, clear=True)
def test_upload_pipeline(mock_process, mock_insert):
    headers = {"X-LogMon-API-Key": "valid_key"}
    
    # 3-1. 손상된 페이로드 (raw_message 누락)
    res_bad = client.post("/api/logmon/upload", json={
        "source_tool": "Cursor", "event_type": "TEST"
    }, headers=headers)
    assert res_bad.status_code == 422
    
    # 3-2. 정상 파이프라인
    mock_insert.return_value = 999
    res_ok = client.post("/api/logmon/upload", json={
        "source_tool": "Cursor", "event_type": "TEST", "raw_message": "test content"
    }, headers=headers)
    
    assert res_ok.status_code == 201
    data = res_ok.json()
    assert data["status"] == "success"
    assert data["log_id"] == 999
    
    # Mock 호출 검증
    mock_insert.assert_called_once()
    
    # 3-3. 멱등성 (Idempotency) 검증
    mock_insert.return_value = None
    res_idem = client.post("/api/logmon/upload", json={
        "source_tool": "Cursor", "event_type": "TEST", "raw_message": "test content"
    }, headers=headers)
    
    assert res_idem.status_code == 201
    assert res_idem.json()["status"] == "skipped"

@patch('backend.api.routes.get_dashboard_stats')
@patch.dict(os.environ, {"ALLOWED_API_KEYS": "valid_key"}, clear=True)
def test_stats_api(mock_stats):
    headers = {"X-LogMon-API-Key": "valid_key"}
    
    mock_stats.return_value = {
        "total_logs": 100,
        "today_tokens": 5000,
        "has_code_ratio": 25.5,
        "trend_7d": [],
        "is_agent_installed": True
    }
    
    res = client.get("/api/logmon/stats", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_logs"] == 100
    assert data["today_tokens"] == 5000
    assert data["has_code_ratio"] == 25.5
    assert data["is_agent_installed"] is True
