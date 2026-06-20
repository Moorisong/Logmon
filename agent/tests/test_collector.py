import os
import json
import pytest
from unittest.mock import patch, mock_open, MagicMock

import urllib.error
from agent.core.checkpoint import get_last_offset, update_offset, CHECKPOINT_FILE
from agent.core.sender import scan_and_send
from agent.config import get_cursor_logs_dir

@pytest.fixture(autouse=True)
def setup_teardown_checkpoint():
    """테스트 전후로 체크포인트 파일 격리 및 삭제"""
    # 임시 체크포인트 지정 (본래 상수로 지정되어 동적 오버라이드가 까다로울 수 있으나,
    # 테스트 구동 시 파일 권한 문제나 오염을 피하기 위해 임시 파일 사용이 좋음.
    # 여기선 기존 파일을 날리고 테스트 후 복원하는 대신 단순히 삭제 처리)
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
    yield
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

# 1. 오프셋 갱신 로직 단위 테스트
def test_offset_logic():
    dummy_filepath = "/tmp/dummy.log"
    
    # 1-1. 최초 상태 (0 반환)
    assert get_last_offset(dummy_filepath) == 0
    
    # 1-2. 갱신 후 정상 반환 확인
    update_offset(dummy_filepath, 1024)
    assert get_last_offset(dummy_filepath) == 1024
    
    # 1-3. 다른 파일 영향 없음 확인
    assert get_last_offset("/tmp/other.log") == 0

# 2. OS 경로 파싱 단위 테스트
@patch('platform.system')
def test_os_routing(mock_system):
    # macOS 모킹
    mock_system.return_value = "Darwin"
    assert "Library/Application Support/Cursor/logs" in get_cursor_logs_dir()
    
    # Windows 모킹
    mock_system.return_value = "Windows"
    assert "Cursor\\logs" in get_cursor_logs_dir() or "Cursor/logs" in get_cursor_logs_dir()

# 3. urllib HTTP 통신 방어 및 실패 롤백 테스트
@patch('agent.core.sender.update_offset')
@patch('urllib.request.urlopen')
@patch('os.path.exists')
@patch('builtins.open', new_callable=mock_open, read_data=b"test new log line\n")
def test_http_sender_error_rollback(mock_file, mock_exists, mock_urlopen, mock_update_offset):
    """
    서버 500 에러 또는 타임아웃 발생 시 오프셋 갱신 로직을 타지 않고 안전하게 스킵되는지 테스트
    """
    mock_exists.return_value = True # 파일 존재함
    m_file_instance = mock_file.return_value
    m_file_instance.tell.return_value = 18
    dummy_file = "/tmp/dummy2.log"
    
    # HTTPError 500 모킹
    error_mock = urllib.error.HTTPError(url="", code=500, msg="Internal Server Error", hdrs={}, fp=None)
    mock_urlopen.side_effect = error_mock
    
    # 실행
    scan_and_send(dummy_file, "http://localhost:8000", "dummy_key")
    
    # 오프셋이 업데이트되지 않아야 함
    mock_update_offset.assert_not_called()

@patch('agent.core.sender.update_offset')
@patch('urllib.request.urlopen')
@patch('os.path.exists')
@patch('builtins.open', new_callable=mock_open, read_data=b"test new log line\n")
def test_http_sender_success(mock_file, mock_exists, mock_urlopen, mock_update_offset):
    """
    전송 성공 시 오프셋이 정상적으로 갱신되는지 테스트
    """
    mock_exists.return_value = True # 파일 존재함
    m_file_instance = mock_file.return_value
    m_file_instance.tell.return_value = 18
    dummy_file = "/tmp/dummy3.log"
    
    # 200 OK 모킹
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response
    
    # 실행
    scan_and_send(dummy_file, "http://localhost:8000", "dummy_key")
    
    # 전송이 성공했으므로 update_offset이 18로 호출되었어야 함
    mock_update_offset.assert_called_once_with(dummy_file, 18)
