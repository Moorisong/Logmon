import os
import sys
import datetime
import logging

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.db.sqlite_handler import insert_activity_log
from backend.db.chroma_handler import process_and_store_vector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_test_data():
    # ALLOWED_API_KEYS에서 첫 번째 키를 사용하거나 기본 개발용 키 사용
    allowed_keys = os.getenv("ALLOWED_API_KEYS", "default_dev_key")
    user_key = allowed_keys.split(",")[0].strip()
    
    logger.info(f"사용자 키 [{user_key}]로 테스트 시드 데이터 적재를 시작합니다.")
    
    now = datetime.datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. 가상 에러 로그 데이터 정의
    error_log = {
        "user_key": user_key,
        "timestamp": now_str,
        "source_tool": "Cursor",
        "event_type": "LOG_DUMP",
        "task_name": "Build",
        "duration_seconds": 12,
        "input_tokens": 150,
        "output_tokens": 80,
        "raw_message": (
            f"{now_str} [error] Connection lost to database host 'db.local'.\n"
            "at pool.js:145:10\n"
            "at Connection.connect (connection.js:80:5)\n"
            "Error: ECONNREFUSED 127.0.0.1:5432"
        ),
        "has_code_block": 1
    }
    
    # 2. 가상 경고 로그 데이터 정의
    warning_log = {
        "user_key": user_key,
        "timestamp": (now - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
        "source_tool": "VSCode",
        "event_type": "LOG_DUMP",
        "task_name": "Lint",
        "duration_seconds": 3,
        "input_tokens": 50,
        "output_tokens": 20,
        "raw_message": (
            f"{(now - datetime.timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')} [warning] "
            "Deprecated API usage detected: 'urllib.request.urlopen' should be replaced with 'httpx.client'."
        ),
        "has_code_block": 0
    }
    
    # SQLite 및 Chroma DB 적재 실행
    for log_data in [error_log, warning_log]:
        try:
            log_id = insert_activity_log(log_data)
            if log_id:
                process_and_store_vector(log_id, log_data)
                logger.info(f"성공적으로 시드 데이터를 적재했습니다 (ID: {log_id}, Type: {log_data['event_type']})")
            else:
                logger.warning("중복된 로그이거나 적재가 생략되었습니다.")
        except Exception as e:
            logger.error(f"시드 데이터 적재 에러 발생: {e}")

if __name__ == "__main__":
    seed_test_data()
