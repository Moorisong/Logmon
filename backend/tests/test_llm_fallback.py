import os
import pytest
import respx
import httpx
from unittest.mock import patch

# --- 테스트 환경 강제 분리 ---
os.environ["LOGMON_ENV"] = "test"
os.environ["LOGMON_DB_DIR"] = "/tmp/logmon_test_llm_fallback_db"
os.environ["LOGMON_CHROMA_DIR"] = "/tmp/logmon_test_llm_fallback_chroma"

from backend.db.connection import init_db, get_connection
from backend.llm.client import query_sqlite_logs, generate_simulated_response, generate_completion
from backend.llm.reranker import rule_based_rerank
from backend.llm.rag_engine import ask_rag_agent

@pytest.fixture(autouse=True)
def setup_and_teardown():
    init_db()
    yield
    if os.path.exists(os.environ["LOGMON_DB_DIR"]):
        import shutil
        shutil.rmtree(os.environ["LOGMON_DB_DIR"], ignore_errors=True)

def test_regexp_sqlite_query():
    """SQLite REGEXP 정규식 기능이 정상 작동하는지 확인"""
    from backend.db.sqlite_handler import insert_activity_log
    
    insert_activity_log({
        "user_key": "test_user",
        "timestamp": "2026-06-21 12:00:00",
        "source_tool": "VSCode",
        "event_type": "ERROR",
        "task_name": "Build",
        "raw_message": "Failed with exception db.local error here"
    })
    
    # "db.local" 정규식 패턴 검색 테스트
    rows = query_sqlite_logs("db.local")
    assert len(rows) > 0
    assert "db.local" in rows[0][4]

def test_light_reranker_logic():
    """룰 베이스 리랭커가 검색 쿼리 단어와의 매칭률에 따라 정상 작동하는지 테스트"""
    docs = [
        "This is a general log entry without error",
        "Connection refused to db.local host, critical failure occurred",
        "Warning message regarding host performance"
    ]
    
    result = rule_based_rerank("db.local failure", docs, top_k=2)
    
    # "db.local host, critical failure occurred"가 매칭 점수가 가장 높아서 최상위에 올라와야 함
    assert "db.local" in result
    assert "critical failure" in result
    assert result.index("db.local") < result.index("general log") if "general log" in result else True

@pytest.mark.asyncio
async def test_rag_agent_global_fallback():
    """RAG 파이프라인 중 Chroma DB나 다른 곳에서 예외가 발생할 때 RAG Agent가 무너지지 않고 SQLite Fallback을 수행하는지 확인"""
    from backend.db.sqlite_handler import insert_activity_log
    
    insert_activity_log({
        "user_key": "test_user",
        "timestamp": "2026-06-21 12:00:00",
        "source_tool": "CLI",
        "event_type": "ERROR",
        "task_name": "Sync",
        "raw_message": "Pipeline crash test message"
    })
    
    # query_vectors에서 강제로 예외를 발생시켜 전체 RAG 파이프라인 에러를 유도
    with patch("backend.llm.rag_engine.query_vectors", side_effect=Exception("Chroma down!")):
        # LOGMON_ENV를 임시로 dev로 바꾸어 Fallback 동작이 발생하게 함
        original_env = os.environ.get("LOGMON_ENV")
        os.environ["LOGMON_ENV"] = "dev"
        try:
            answer = await ask_rag_agent("Pipeline crash", "test_user")
            
            assert "안녕" in answer
            assert "실제 저장된 로그 데이터" in answer
            assert "LogLevel: ERROR" in answer
        finally:
            if original_env is not None:
                os.environ["LOGMON_ENV"] = original_env
            else:
                del os.environ["LOGMON_ENV"]
