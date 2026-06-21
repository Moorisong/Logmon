import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 라우터 및 DB 커넥션 로드
from backend.api.routes import router as logmon_router
from backend.db.connection import get_connection

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
        conn = get_connection()
        conn.close()
        logger.info("데이터베이스 레이어 초기화 통과.")
    except Exception as e:
        logger.error(f"데이터베이스 레이어 초기화 실패: {e}")

@app.get("/")
def read_root():
    return {"status": "healthy", "service": "LogMon Backend"}

# [★ 핵심 교통정리] 
# routes.py 내부 자체에 prefix="/api/logmon"이 이미 내장되어 있으므로, 
# 마운트할 때는 중복 prefix 없이 그대로 밀어 넣어 주어야 주소 파싱 오류(404)가 나지 않습니다.
app.include_router(logmon_router)

# 정적 파일 에셋 스트리밍을 위한 마운트 (도커 내부 absolute path 기준)
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")