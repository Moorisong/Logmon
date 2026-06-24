import os
import datetime
import logging
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Request
from fastapi.responses import PlainTextResponse, FileResponse
from pydantic import BaseModel

from backend.api.dependencies import verify_api_key
from backend.db.sqlite_handler import insert_activity_log, get_dashboard_stats
from backend.db.chroma_handler import process_and_store_vector
from backend.llm.rag_engine import ask_rag_agent

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
    file_path: Optional[str] = "UNKNOWN"

class ChatRequest(BaseModel):
    question: str

def run_chroma_pipeline(log_id: int, data: dict):
    """
    백그라운드에서 실행될 Chroma DB 임베딩/적재 파이프라인
    """
    try:
        process_and_store_vector(log_id, data)
    except Exception as e:
        logger.error(f"백그라운드 Chroma DB 적재 실패 (log_id: {log_id}): {e}")

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_log(
    payload: LogPayload, 
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    수집기 에이전트로부터 로그를 전송받아 SQLite에 적재하고, 백그라운드에서 Chroma DB 처리를 트리거합니다.
    """
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    data = payload.model_dump()
    data["user_key"] = api_key
    data["timestamp"] = now_str
    
    try:
        log_id = insert_activity_log(data)
    except Exception as e:
        logger.error(f"SQLite 3 적재 에러: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database persistence error"
        )
        
    if log_id is None:
        return {"status": "skipped", "detail": "Log already exists (Idempotent request)"}
        
    # Chroma DB 임베딩 적재 (백그라운드 태스크)
    background_tasks.add_task(run_chroma_pipeline, log_id, data)
    
    return {"status": "success", "processed_records": 1, "log_id": log_id}

@router.post("/chat", status_code=status.HTTP_200_OK)
async def chat_with_logmon(
    payload: ChatRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    사용자의 질문을 받아 RAG 엔진을 거쳐 답변을 생성합니다.
    """
    try:
        answer = await ask_rag_agent(question=payload.question, user_key=api_key)
        return {"answer": answer}
    except Exception as e:
        logger.error(f"챗봇 오류: {e}")
        return {"answer": "현재 AI 엔진 서비스가 일시 점검 중입니다."}

@router.get("/stats", status_code=status.HTTP_200_OK)
async def get_stats(api_key: str = Depends(verify_api_key)):
    """
    대시보드 통계 및 에이전트 동적 상태(설치 여부 / 온라인 여부) 반환
    """
    try:
        stats_data = get_dashboard_stats(user_key=api_key)
        if stats_data is None:
            stats_data = {}
            
        # 1. [동적 판단] 설치 여부: DB에 데이터가 1개라도 있으면 대시보드 화면 활성화
        total_logs = stats_data.get("total_logs", 0)
        stats_data["is_agent_installed"] = total_logs > 0
            
        # 2. [동적 판단] 온라인 여부: 마지막 데이터 수집 시간이 10분 이내인지 판별
        is_online = False
        last_sync_str = stats_data.get("last_sync_time")
        
        if last_sync_str:
            try:
                # SQLite의 타임스탬프 형식 안전 파싱 (밀리초, T문자열 제거)
                clean_time_str = last_sync_str.split(".")[0].replace("T", " ")
                last_sync = datetime.datetime.strptime(clean_time_str, "%Y-%m-%d %H:%M:%S")
                
                # 서버-DB 간 시간차이를 절대값으로 계산하여 타임존 꼬임 문제 방어
                diff_seconds = abs((datetime.datetime.now() - last_sync).total_seconds())
                
                # 600초(10분) 이내에 데이터가 들어왔다면 온라인으로 표시
                if diff_seconds <= 600:
                    is_online = True
            except Exception as e:
                logger.warning(f"시간 파싱 실패: {e}")
        
        stats_data["is_online"] = is_online
            
        return stats_data
    except Exception as e:
        logger.error(f"통계 API 호출 실패: {e}")
        return {"is_online": False, "total_logs": 0, "trend_7d": [], "is_agent_installed": False}

# =========================================================================
# 아래부터 CLI 에이전트 동적 설치 & 정적 파일 제공 로직 (완전 복원)
# =========================================================================

def get_primary_api_key():
    """서버에 설정된 API Key를 가져옵니다. (동적 치환용)"""
    raw_keys = os.getenv("ALLOWED_API_KEYS", os.getenv("LOGMON_API_KEY", "default_dev_key"))
    if raw_keys:
        return raw_keys.split(",")[0].strip()
    return "default_dev_key"

@router.get("/agent-setup-script", response_class=PlainTextResponse)
async def serve_agent_setup_script(request: Request):
    """설치 스크립트 제공 및 동적 변수 치환"""
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        script_path = os.path.join(base_dir, "static", "install-agent.sh")
        
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        real_host = "https://logmon.haroo.site"
        api_key = get_primary_api_key()
        
        content = content.replace('BACKEND_URL="http://localhost:3008"', f'BACKEND_URL="{real_host}"')
        content = content.replace('API_KEY="default_dev_key"', f'API_KEY="{api_key}"')
        
        return content
    except Exception as e:
        logger.error(f"설치 스크립트 로드 실패: {e}")
        return 'echo "❌ 서버에서 설치 스크립트를 찾을 수 없습니다."\nexit 1'

@router.get("/agent-uninstall-script", response_class=PlainTextResponse)
async def serve_agent_uninstall_script(request: Request):
    """제거 스크립트 제공 및 동적 변수 치환"""
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        script_path = os.path.join(base_dir, "static", "uninstall-agent.sh")
        
        if not os.path.exists(script_path):
            return 'echo "❌ 서버에 uninstall-agent.sh 파일이 없습니다."\nexit 1'
            
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        real_host = "https://logmon.haroo.site"
        api_key = get_primary_api_key()
        
        content = content.replace('BACKEND_URL="http://localhost:3008"', f'BACKEND_URL="{real_host}"')
        content = content.replace('API_KEY="default_dev_key"', f'API_KEY="{api_key}"')
        
        return content
    except Exception as e:
        logger.error(f"제거 스크립트 로드 실패: {e}")
        return 'echo "❌ 서버에서 제거 스크립트를 찾을 수 없습니다."\nexit 1'

@router.get("/static/{filename}")
async def serve_static_files(filename: str):
    """에이전트가 다운로드하는 세부 파이썬/설정 파일들 서빙"""
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        file_path = os.path.join(base_dir, "static", filename)
        
        if os.path.exists(file_path):
            return FileResponse(file_path)
        else:
            raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        logger.error(f"정적 파일 서빙 에러: {e}")
        raise HTTPException(status_code=404, detail="File not found")