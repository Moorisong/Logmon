import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, status, BackgroundTasks
from pydantic import BaseModel

# 로거 초기화
logger = logging.getLogger(__name__)

# 라우터 객체 정의
router = APIRouter(prefix="/api/logmon", tags=["Logmon Agent API"])

# Pydantic 모델 정의
class LogPayload(BaseModel):
    source_tool: str
    event_type: str
    raw_message: str
    task_name: Optional[str] = "UNKNOWN"
    duration_seconds: Optional[int] = 0
    input_tokens: Optional[int] = 0
    output_tokens: Optional[int] = 0
    has_code_block: Optional[int] = 0

class ChatRequest(BaseModel):
    question: str

# 의존성 및 DB/RAG 함수 임포트
from backend.api.dependencies import verify_api_key
from backend.db.sqlite_handler import insert_activity_log, get_dashboard_stats
from backend.llm.rag_engine import ask_rag_agent

@router.get("/stats", status_code=status.HTTP_200_OK)
async def get_stats(api_key: str = Depends(verify_api_key)):
    try:
        stats_data = get_dashboard_stats(api_key)
        if stats_data is None: stats_data = {}
        stats_data["is_online"] = True
        return stats_data
    except Exception as e:
        logger.error(f"통계 API 호출 실패: {e}")
        return {"is_online": False, "total_logs": 0, "trend_7d": [], "is_agent_installed": False}

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_log(payload: LogPayload, background_tasks: BackgroundTasks, api_key: str = Depends(verify_api_key)):
    try:
        # 1. 페이로드 데이터를 딕셔너리로 변환
        log_data = payload.dict()
        
        # 2. 필수 필드 주입: user_key와 timestamp
        log_data["user_key"] = api_key
        log_data["timestamp"] = datetime.now().isoformat() # 현재 시간 자동 삽입
        
        # 3. DB 저장
        insert_activity_log(log_data)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"로그 업로드 실패: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/chat", status_code=status.HTTP_200_OK)
async def chat_with_logmon(payload: ChatRequest, api_key: str = Depends(verify_api_key)):
    try:
        # RAG 엔진 호출
        answer = await ask_rag_agent(question=payload.question, user_key=api_key)
        return {"answer": answer}
    except Exception as e:
        logger.error(f"챗봇 오류: {e}")
        return {"answer": "현재 AI 엔진 서비스가 일시 점검 중입니다."}