# backend/tests/test_llm_stats.py
import os
import pytest
import datetime
from unittest.mock import patch

# 테스트 환경 강제 분리
os.environ["LOGMON_ENV"] = "test"
os.environ["LOGMON_DB_DIR"] = "/tmp/logmon_test_llm_stats_db"
os.environ["LOGMON_CHROMA_DIR"] = "/tmp/logmon_test_llm_stats_chroma"

from backend.db.connection import init_db, get_connection
from backend.db.sqlite_logs import insert_activity_log
from backend.llm.utils import upsert_daily_statistics

@pytest.fixture(autouse=True)
def setup_and_teardown():
    init_db()
    yield
    if os.path.exists(os.environ["LOGMON_DB_DIR"]):
        import shutil
        shutil.rmtree(os.environ["LOGMON_DB_DIR"], ignore_errors=True)

@patch('backend.db.chroma_handler.get_collection')
def test_upsert_daily_statistics_flow(mock_get_col):
    """1. 통계 요약 데이터 upsert_daily_statistics 기본 동작 흐름 검증"""
    log_data = {
        "user_key": "test_key",
        "source_tool": "VSCode",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d 10:00:00"),
        "event_type": "INFO",
        "task_name": "Build_Engine",
        "duration_seconds": 3600,
        "input_tokens": 500,
        "output_tokens": 500,
        "raw_message": "Build completed successfully",
        "has_code_block": 0
    }
    insert_activity_log(log_data)
    
    upsert_daily_statistics("test_key")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT raw_message FROM ide_activity_logs 
        WHERE user_key = 'test_key' AND task_name = 'STATISTICS'
    """)
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert "[STATISTICS]" in row[0]
    assert "Total_Usage_Time: 1.0 Hours" in row[0]
    assert "Total_AI_Tokens_Used: 1000 Tokens" in row[0]

@patch('backend.db.chroma_handler.get_collection')
def test_upsert_daily_statistics_levels(mock_get_col):
    """2. INFO/WARN/ERROR 로그 건수가 정확히 카운트되는지 검증"""
    base_time = datetime.datetime.now().strftime("%Y-%m-%d")
    logs = [
        {"user_key": "test_key", "event_type": "INFO", "timestamp": f"{base_time} 10:00:01", "task_name": "Task1", "raw_message": "msg1"},
        {"user_key": "test_key", "event_type": "WARN", "timestamp": f"{base_time} 10:00:02", "task_name": "Task2", "raw_message": "msg2"},
        {"user_key": "test_key", "event_type": "ERROR", "timestamp": f"{base_time} 10:00:03", "task_name": "Task3", "raw_message": "ConnectionError Exception"},
    ]
    for log in logs:
        insert_activity_log(log)
        
    upsert_daily_statistics("test_key")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT raw_message FROM ide_activity_logs WHERE user_key = 'test_key' AND task_name = 'STATISTICS'")
    row = cursor.fetchone()
    conn.close()
    
    assert "Total_Log_Count: 3 Cases" in row[0]
    assert "INFO: 1" in row[0]
    assert "WARN: 1" in row[0]
    assert "ERROR: 1" in row[0]

@patch('backend.db.chroma_handler.get_collection')
def test_upsert_daily_statistics_top_errors(mock_get_col):
    """3. 에러 종류 Top 3가 빈도 기반으로 정확히 파싱되는지 검증"""
    base_time = datetime.datetime.now().strftime("%Y-%m-%d")
    logs = [
        {"user_key": "test_key", "event_type": "ERROR", "timestamp": f"{base_time} 10:01:00", "raw_message": "TimeoutException occurred"},
        {"user_key": "test_key", "event_type": "ERROR", "timestamp": f"{base_time} 10:02:00", "raw_message": "TimeoutException again"},
        {"user_key": "test_key", "event_type": "ERROR", "timestamp": f"{base_time} 10:03:00", "raw_message": "PermissionError denied"},
    ]
    for log in logs:
        insert_activity_log(log)
        
    upsert_daily_statistics("test_key")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT raw_message FROM ide_activity_logs WHERE user_key = 'test_key' AND task_name = 'STATISTICS'")
    row = cursor.fetchone()
    conn.close()
    
    assert "TimeoutException: 2" in row[0]
    assert "PermissionError: 1" in row[0]

@patch('backend.db.chroma_handler.get_collection')
def test_upsert_daily_statistics_empty(mock_get_col):
    """4. 로그가 없을 때의 디폴트 처리 검증"""
    upsert_daily_statistics("empty_key")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT raw_message FROM ide_activity_logs WHERE user_key = 'empty_key' AND task_name = 'STATISTICS'")
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert "Total_Usage_Time: 0.0 Hours" in row[0]
    assert "Top_Error_Types: [None]" in row[0]

@patch('backend.db.chroma_handler.get_collection')
def test_upsert_daily_statistics_update(mock_get_col):
    """5. 기존에 statistics 요약이 있을 때 신규 데이터로 덮어쓰기 업데이트가 잘 되는지 검증"""
    base_time = datetime.datetime.now().strftime("%Y-%m-%d")
    insert_activity_log({"user_key": "test_key", "event_type": "INFO", "timestamp": f"{base_time} 10:00:00", "duration_seconds": 100})
    upsert_daily_statistics("test_key")
    
    # 두 번째 로그 삽입 후 다시 집계
    insert_activity_log({"user_key": "test_key", "event_type": "INFO", "timestamp": f"{base_time} 11:00:00", "duration_seconds": 200})
    upsert_daily_statistics("test_key")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(id) FROM ide_activity_logs WHERE user_key = 'test_key' AND task_name = 'STATISTICS'")
    count = cursor.fetchone()[0]
    conn.close()
    
    assert count == 1 # 덮어쓰기 되었으므로 레코드는 여전히 1개여야 함

@patch('backend.db.chroma_handler.get_collection')
def test_upsert_daily_statistics_duration_calculation(mock_get_col):
    """6. 시간 계산이 정확히 Hours로 반올림되는지 검증"""
    base_time = datetime.datetime.now().strftime("%Y-%m-%d")
    insert_activity_log({"user_key": "test_key", "event_type": "INFO", "timestamp": f"{base_time} 10:00:00", "duration_seconds": 5400}) # 1.5 Hours
    upsert_daily_statistics("test_key")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT raw_message FROM ide_activity_logs WHERE user_key = 'test_key' AND task_name = 'STATISTICS'")
    row = cursor.fetchone()
    conn.close()
    
    assert "Total_Usage_Time: 1.5 Hours" in row[0]

@patch('backend.db.chroma_handler.get_collection')
def test_upsert_daily_statistics_token_summation(mock_get_col):
    """7. 토큰 합산이 정확히 되는지 검증"""
    base_time = datetime.datetime.now().strftime("%Y-%m-%d")
    insert_activity_log({"user_key": "test_key", "event_type": "INFO", "timestamp": f"{base_time} 10:00:00", "input_tokens": 120, "output_tokens": 80})
    insert_activity_log({"user_key": "test_key", "event_type": "INFO", "timestamp": f"{base_time} 10:05:00", "input_tokens": 200, "output_tokens": 300})
    upsert_daily_statistics("test_key")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT raw_message FROM ide_activity_logs WHERE user_key = 'test_key' AND task_name = 'STATISTICS'")
    row = cursor.fetchone()
    conn.close()
    
    assert "Total_AI_Tokens_Used: 700 Tokens" in row[0]
