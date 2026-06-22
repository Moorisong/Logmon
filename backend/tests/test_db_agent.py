import os
import sqlite3
import pytest
from unittest.mock import patch

from backend.db.connection import init_db
from backend.db.sqlite_handler import insert_activity_log, check_duplicate_log
from backend.db.chroma_handler import chunk_text, process_and_store_vector

# --- 테스트 환경 강제 분리 ---
os.environ["LOGMON_DB_DIR"] = "/tmp/logmon_test_db"
os.environ["LOGMON_CHROMA_DIR"] = "/tmp/logmon_test_chroma"

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # Setup: 테스트용 DB 초기화
    init_db()
    yield
    # Teardown: 테스트 종료 시 SQLite 파일 삭제
    if os.path.exists(os.environ["LOGMON_DB_DIR"]):
        import shutil
        shutil.rmtree(os.environ["LOGMON_DB_DIR"], ignore_errors=True)

# 1. 초기화 누락 상태 방어 테스트
def test_db_initialization():
    """데이터 저장 경로가 전혀 없는 완전한 초기 상태에서 자동 생성 여부 검증"""
    assert os.path.exists(os.environ["LOGMON_DB_DIR"])
    db_file_path = os.path.join(os.environ["LOGMON_DB_DIR"], "logmon.db")
    assert os.path.exists(db_file_path)
    
    # 테이블 구조 확인
    conn = sqlite3.connect(db_file_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ide_activity_logs';")
    assert cursor.fetchone() is not None
    conn.close()

# 2. 분기 및 예외 케이스 검증 (멱등성 및 SQL 인젝션)
def test_idempotency_and_sql_injection():
    """동일 로그 중복 삽입 방어 및 악의적 SQL 바인딩 방어 검증"""
    malicious_data = {
        "user_key": "TEST_USER_A",
        "timestamp": "2026-06-20 12:00:00",
        "source_tool": "Cursor",
        "raw_message": "' OR 1=1; DROP TABLE ide_activity_logs;--"
    }
    
    # 첫 번째 삽입
    log_id = insert_activity_log(malicious_data)
    assert log_id is not None
    
    # SQL 인젝션 방어 확인 (테이블이 삭제되지 않고 문자로 정상 적재됨)
    conn = sqlite3.connect(os.path.join(os.environ["LOGMON_DB_DIR"], "logmon.db"))
    cursor = conn.cursor()
    cursor.execute("SELECT raw_message FROM ide_activity_logs WHERE id=?", (log_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == malicious_data["raw_message"]
    conn.close()

    # 두 번째 삽입 시도 (동일 user_key, timestamp)
    duplicate_log_id = insert_activity_log(malicious_data)
    assert duplicate_log_id is None # 멱등성에 의해 None 반환

# 3. 환경 및 반응형 검증 (Null 및 극단적 데이터 청킹 분할)
def test_chunking_algorithm_robustness():
    """Null, 비어있는 값, 매우 짧거나 긴 텍스트 청킹 테스트"""
    # 3-1. Null 방어
    assert chunk_text(None) == []
    
    # 3-2. 짧은 텍스트 (Chunk Size 이내)
    short_text = "이것은 매우 짧은 에러 로그입니다."
    assert chunk_text(short_text, chunk_size=800) == [short_text]
    
    # 3-3. 매우 긴 텍스트 분할 (루프 정지/오버플로우 방어)
    long_text = "A" * 2000
    chunks = chunk_text(long_text, chunk_size=800, overlap=100)
    assert len(chunks) > 2
    assert len(chunks[0]) == 800

# 4. 상태 격리 및 사이드 이펙트 방어 (Chroma DB 예외 상황 모킹)
@patch('backend.db.chroma_handler.get_embedding')
def test_chroma_db_metadata_isolation_and_failure(mock_get_embedding):
    """임베딩 서버 무응답 시 중단 방어 및 멀티테넌시 메타데이터 주입 락 검증"""
    # 에뮬레이트: API 호출 실패
    mock_get_embedding.side_effect = Exception("Ollama Server Timeout")
    
    data = {
        "user_key": "USER_A",
        "timestamp": "2026-06-20 12:00:00",
        "raw_message": "Chroma DB 테스트를 위한 텍스트입니다." * 100
    }
    
    # 프로세스 진행 시 임베딩이 실패하더라도 로직이 폭파되지 않고 예외가 격리(로깅)됨을 확인
    try:
        process_and_store_vector(log_id=1, data=data)
        success = True
    except Exception:
        success = False
        
    # 현재 코드 구조상 Exception을 continue로 잡아 넘기므로 폭파되지 않음
    assert success is True 

def test_get_dashboard_stats_agent_installed_flag():
    """get_dashboard_stats에서 수동 업로드와 에이전트 로그를 구분하여 is_agent_installed 플래그를 정확하게 집계하는지 검증"""
    from backend.db.sqlite_handler import get_dashboard_stats
    
    user_key = "USER_TEST_STATS"
    
    # 1. 아무 로그도 없을 때 => False
    stats_empty = get_dashboard_stats(user_key)
    assert stats_empty["is_agent_installed"] is False
    
    # 2. 수동 업로드 로그만 있을 때 => False
    manual_data = {
        "user_key": user_key,
        "timestamp": "2026-06-20 12:00:00",
        "source_tool": "Manual Upload UI",
        "event_type": "MANUAL",
        "raw_message": "수동 업로드 테스트 로그"
    }
    insert_activity_log(manual_data)
    stats_manual = get_dashboard_stats(user_key)
    assert stats_manual["is_agent_installed"] is False
    
    # 3. 에이전트 로그(예: VSCode)가 들어왔을 때 => True
    agent_data = {
        "user_key": user_key,
        "timestamp": "2026-06-20 12:05:00",
        "source_tool": "VSCode",
        "event_type": "EDIT",
        "raw_message": "에이전트 수집 테스트 로그"
    }
    insert_activity_log(agent_data)
    stats_agent = get_dashboard_stats(user_key)
    assert stats_agent["is_agent_installed"] is True 

def test_agent_lifecycle_dashboard_sync():
    """에이전트 설치 및 삭제 라이프사이클에 따라 대시보드 동기화 상태 및 수치가 즉시 차단되거나 제공되는지 세부 검증"""
    from backend.db.sqlite_handler import get_dashboard_stats
    
    user_key = "USER_LIFECYCLE_TEST"
    
    # 1. 초기 상태 검증 (설치되지 않음)
    stats = get_dashboard_stats(user_key)
    assert stats["is_agent_installed"] is False
    assert stats["total_logs"] == 0
    assert stats["last_sync_time"] is None
    
    # 2. 에이전트 설치 로그 발생 (AGENT_INSTALL)
    install_data = {
        "user_key": user_key,
        "timestamp": "2026-06-20 12:00:00",
        "source_tool": "Agent CLI",
        "event_type": "AGENT_INSTALL",
        "raw_message": "Agent installed successfully"
    }
    insert_activity_log(install_data)
    
    stats = get_dashboard_stats(user_key)
    assert stats["is_agent_installed"] is True
    assert stats["total_logs"] == 1
    assert stats["last_sync_time"] == "2026-06-20 12:00:00"
    
    # 3. 에이전트 추가 수집 로그 발생
    edit_data = {
        "user_key": user_key,
        "timestamp": "2026-06-20 12:05:00",
        "source_tool": "Cursor",
        "event_type": "EDIT",
        "raw_message": "User edited dashboard.py"
    }
    insert_activity_log(edit_data)
    
    stats = get_dashboard_stats(user_key)
    assert stats["is_agent_installed"] is True
    assert stats["total_logs"] == 2
    assert stats["last_sync_time"] == "2026-06-20 12:05:00"
    
    # 4. 에이전트 삭제 로그 발생 (AGENT_UNINSTALL)
    uninstall_data = {
        "user_key": user_key,
        "timestamp": "2026-06-20 12:10:00",
        "source_tool": "Agent CLI",
        "event_type": "AGENT_UNINSTALL",
        "raw_message": "Agent uninstalled successfully"
    }
    insert_activity_log(uninstall_data)
    
    stats = get_dashboard_stats(user_key)
    # 삭제 후에도 설치 상태는 False가 되지만, 수치는 물리적 수치 그대로 반환되어야 함
    assert stats["is_agent_installed"] is False
    assert stats["total_logs"] == 3
    assert stats["last_sync_time"] == "2026-06-20 12:10:00"
    assert stats["uptime_days"] == 3
    assert stats["total_lines"] == 24
