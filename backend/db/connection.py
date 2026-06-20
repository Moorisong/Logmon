import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

# 기본 DB 경로는 컨테이너 기준. 
def get_db_dir():
    return os.getenv("LOGMON_DB_DIR", "/app/data/db")

def get_db_path():
    return os.path.join(get_db_dir(), "logmon.db")

def init_db():
    """
    SQLite 데이터베이스 및 테이블 초기화
    """
    db_dir = get_db_dir()
    db_path = get_db_path()
    if not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"데이터베이스 디렉토리 생성 완료: {db_dir}")
        except Exception as e:
            logger.error(f"디렉토리 생성 실패: {e}")
            raise

    # 연결 및 초기화 
    # try-finally를 통해 안전하게 close
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # ide_activity_logs 테이블 생성 (Logmon-db-specification.md 기준)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ide_activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_key TEXT NOT NULL,
                source_tool TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                task_name TEXT NOT NULL DEFAULT 'UNKNOWN',
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                raw_message TEXT,
                has_code_block INTEGER NOT NULL DEFAULT 0
            );
        """)
        
        # 인덱스 생성
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_user_time 
            ON ide_activity_logs(user_key, timestamp);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_event_type 
            ON ide_activity_logs(event_type);
        """)
        
        conn.commit()
        logger.info(f"SQLite 3 초기화 완료: {db_path}")
    except sqlite3.Error as e:
        logger.error(f"SQLite 초기화 에러: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    """
    SQLite DB 커넥션을 반환합니다.
    동시성 제어를 위해 timeout 설정과 isolation_level 을 지정합니다.
    """
    try:
        # timeout을 주어 Database Lock 이슈 완화
        conn = sqlite3.connect(get_db_path(), timeout=10.0, isolation_level=None)
        # 쿼리 시 dict 형태로 반환 접근을 위해 row_factory 사용 가능 (옵션)
        # conn.row_factory = sqlite3.Row 
        return conn
    except sqlite3.Error as e:
        logger.error(f"SQLite DB 연결 실패: {e}")
        raise
