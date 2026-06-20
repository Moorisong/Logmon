import datetime
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
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
        # 이미 SQLite에는 적재되었으므로 에러 로그만 남김
        logger.error(f"백그라운드 Chroma DB 적재 실패 (log_id: {log_id}): {e}")

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_log(
    payload: LogPayload, 
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    수집기 에이전트로부터 로그를 전송받아 SQLite에 적재하고,
    백그라운드에서 Chroma DB 벡터 처리를 트리거합니다.
    (Pydantic을 통한 페이로드 검증 실패 시 자동 422 에러 응답)
    """
    # 1. DB 적재를 위한 데이터 구성
    # API 요청을 받은 현재 시각을 기본 timestamp로 지정 (또는 클라이언트가 전송할 수 있음)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    data = payload.model_dump()
    data["user_key"] = api_key
    data["timestamp"] = now_str
    
    # 2. SQLite 3 적재 (Idempotency 처리 포함)
    try:
        log_id = insert_activity_log(data)
    except Exception as e:
        logger.error(f"SQLite 3 적재 에러: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database persistence error"
        )
        
    # 멱등성에 의해 중복 처리된 경우 (None 반환 시)
    if log_id is None:
        return {
            "status": "skipped",
            "detail": "Log already exists (Idempotent request)"
        }
        
    # 3. Chroma DB 임베딩 적재 (백그라운드 태스크)
    background_tasks.add_task(run_chroma_pipeline, log_id, data)
    
    # 4. 용량 상한선 및 TTL 모니터링 (백그라운드 태스크)
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
        # 1. 먼저 7일 TTL 클리닝 수행
        ttl_deleted_ids = cleanup_ttl_logs()
        if ttl_deleted_ids:
            delete_vectors_by_log_ids(ttl_deleted_ids)
            
        # 2. 용량 상한선(Hard Cap) 체크 (500MB)
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
    
    return {
        "answer": answer
    }

@router.get("/stats", status_code=status.HTTP_200_OK)
async def get_stats(
    api_key: str = Depends(verify_api_key)
):
    """
    프론트엔드 대시보드 화면 렌더링에 필요한 통계 데이터를 반환합니다.
    """
    stats_data = get_dashboard_stats(user_key=api_key)
    return stats_data
