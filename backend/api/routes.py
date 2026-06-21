import datetime
import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Response
from fastapi.responses import FileResponse  # <-- 정적 파일 직통 스트리밍 서빙을 위해 추가
from pydantic import BaseModel

from backend.api.dependencies import verify_api_key
from backend.db.sqlite_handler import insert_activity_log, get_dashboard_stats
from backend.db.chroma_handler import process_and_store_vector
from backend.llm.rag_engine import ask_rag_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logmon", tags=["Logmon Agent API"])

class LogPayload(BaseModel):
    source_tool: str
    event_type: str
    raw_message: str
    # 선택적 메타데이터
    task_name: Optional[str] = "UNKNOWN"
    duration_seconds: Optional[int] = 0
    input_tokens: Optional[int] = 0
    output_tokens: Optional[int] = 0
    has_code_block: Optional[int] = 0

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

@router.get("/agent-setup-script", status_code=status.HTTP_200_OK)
async def get_install_script():
    """
    서버의 API Key와 가비아 도메인 주소를 install-agent.sh에 
    동적으로 주입하여 에이전트(CLI)에게 문자열 텍스트로 반환합니다.
    """
    script_path = "backend/static/install-agent.sh"
    if not os.path.exists(script_path):
        script_path = os.path.join(os.path.dirname(__file__), "..", "static", "install-agent.sh")

    try:
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"설치 스크립트 파일을 읽을 수 없습니다: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Installation script source file not found"
        )
    
    # 쉘 템플릿 파일 내부 텍스트 중복 누적 완벽 차단 안전장치
    if "#!/usr/bin/env bash" in content:
        parts = content.split("#!/usr/bin/env bash")
        if len(parts) > 2:
            content = "#!/usr/bin/env bash" + parts[1]
    
    allowed_keys = os.getenv("ALLOWED_API_KEYS", "default_dev_key")
    primary_key = allowed_keys.split(",")[0].strip() 
    
    # 가비아 SSL 서브도메인을 베이스 URL로 안전하게 고정
    server_url = "https://logmon.haroo.site" 

    # 쉘 스크립트 내부 템플릿 변수를 서버 환경 변수로 완벽 치환
    content = content.replace('BACKEND_URL="http://localhost:3008"', f'BACKEND_URL="{server_url}"')
    content = content.replace('API_KEY="default_dev_key"', f'API_KEY="{primary_key}"')

    return Response(content=content, media_type="text/plain")

# [★핵심 기능] Nginx가 안전하게 토스해주는 /api/logmon/static/ 파일 요청을 직접 받아서 파일로 안전하게 응답합니다.
@router.get("/static/{file_name}")
async def get_static_file(file_name: str):
    """
    에이전트 구동에 필요한 핵심 파이썬 소스 파일들을 
    도커 내부 경로에서 직접 탐색하여 스트리밍 다운로드 서빙합니다.
    """
    static_dir = "backend/static"
    if not os.path.exists(static_dir):
        static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
        
    file_path = os.path.join(static_dir, file_name)
    
    if not os.path.exists(file_path):
        logger.error(f"요청된 정적 파일을 찾을 수 없습니다: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"File {file_name} not found in static repository."
        )
        
    # 파일 확장자에 따른 적절한 미디어 타입 반환
    media_type = "application/x-python" if file_name.endswith(".py") else "text/plain"
    return FileResponse(path=file_path, media_type=media_type, filename=file_name)

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_log(
    payload: LogPayload, 
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    수집기 에이전트로부터 로그를 전송받아 SQLite에 적재하고,
    백그라운드에서 Chroma DB 벡터 처리를 트리거합니다.
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
        return {
            "status": "skipped",
            "detail": "Log already exists (Idempotent request)"
        }
        
    background_tasks.add_task(run_chroma_pipeline, log_id, data)
    background_tasks.add_task(run_capacity_check_pipeline)
    
    return {
        "status": "success",
        "processed_records": 1,
        "log_id": log_id
    }

def run_capacity_check_pipeline():
    from backend.db.sqlite_handler import get_total_db_size_mb, cleanup_old_logs, cleanup_ttl_logs
    from backend.db.chroma_handler import delete_vectors_by_log_ids
    
    try:
        ttl_deleted_ids = cleanup_ttl_logs()
        if ttl_deleted_ids:
            delete_vectors_by_log_ids(ttl_deleted_ids)
            
        max_mb = 500.0
        while True:
            current_mb = get_total_db_size_mb()
            if current_mb > max_mb:
                logger.info(f"Hard Cap 초과 (현재: {current_mb:.2f}MB / 최대: {max_mb}MB). FIFO 클리닝 시작...")
                fifo_deleted_ids = cleanup_old_logs(limit=100)
                if not fifo_deleted_ids:
                    break
                delete_vectors_by_log_ids(fifo_deleted_ids)
            else:
                break
    except Exception as e:
        logger.error(f"용량 체크 파이프라인 에러: {e}")

@router.post("/chat", status_code=status.HTTP_200_OK)
async def chat_with_logmon(
    payload: ChatRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    사용자의 질문을 받아 RAG 엔진을 거쳐 Ollama 기반으로 답변을 생성합니다.
    """
    answer = await ask_rag_agent(question=payload.question, user_key=api_key)
    return {"answer": answer}

@router.get("/stats", status_code=status.HTTP_200_OK)
async def get_stats(
    api_key: str = Depends(verify_api_key)
):
    """
    프론트엔드 대시보드 화면 렌더링에 필요한 통계 데이터를 반환합니다.
    """
    stats_data = get_dashboard_stats(user_key=api_key)
    return stats_data