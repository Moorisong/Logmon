import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from backend.db.connection import init_db
from backend.api.routes import router as logmon_router

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backend_main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 애플리케이션 시작 전 (Startup)
    logger.info("Logmon Backend API Gateway 기동 중...")
    try:
        # SQLite DB 및 데이터 경로 초기화 보장
        init_db()
        logger.info("데이터베이스 레이어 초기화 통과.")
    except Exception as e:
        logger.error(f"데이터베이스 초기화 실패: {e}")
        # 서버를 내리는 대신 로그만 남길 수 있음
        
    yield
    # 애플리케이션 종료 시 (Shutdown)
    logger.info("Logmon Backend API Gateway 종료 중...")

# FastAPI 애플리케이션 생성
app = FastAPI(
    title="Logmon Backend API Gateway",
    description="Agent 데이터 수집 및 UI/RAG 백엔드 서버",
    version="1.0.0",
    docs_url="/api/logmon/docs",
    openapi_url="/api/logmon/openapi.json",
    lifespan=lifespan
)

# 사용자 요청(MVP 확정 사항)에 따른 CORS 와일드카드 개방
# (동일 호스트 기반 Nginx 라우팅 환경을 고려)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(logmon_router)

# 정적(Static) 배포 경로 확보 (에이전트 바이너리/쉘스크립트용)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)
    
app.mount("/api/logmon/static", StaticFiles(directory=static_dir), name="static")

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}
