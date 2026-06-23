import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

# 라우터 및 DB 커넥션 로드
from backend.api.routes import router as logmon_router
from backend.db.connection import get_connection
from backend.db.sqlite_logs import init_db  # 👈 [핵심] 아까 만든 함수 불러오기!

# 로깅 바인딩
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LogMon API Gateway",
    description="LogMon 시스템 인프라 백엔드 게이트웨이",
    version="1.0.0"
)

# CORS 보안 설정 미들웨어
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    logger.info("Logmon Backend API Gateway 기동 중...")
    try:
        init_db() # 👈 [핵심] 여기서 테이블 생성 함수를 무조건 실행합니다!
        logger.info("데이터베이스 레이어 초기화 통과.")
    except Exception as e:
        logger.error(f"데이터베이스 레이어 초기화 실패: {e}")

@app.get("/")
def read_root():
    return {"status": "healthy", "service": "LogMon Backend"}

app.include_router(logmon_router)

# 정적 파일 에셋 스트리밍을 위한 마운트
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")