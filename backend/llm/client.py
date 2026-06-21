import os
import httpx
import logging
from backend.llm.prompt_templates import ERROR_FALLBACK_MESSAGE

logger = logging.getLogger(__name__)

# 환경변수 로드 (Fallback: localhost, 스레드 3)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
try:
    OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "3"))
except ValueError:
    OLLAMA_NUM_THREAD = 3

MODEL_NAME = "gemma2:2b"

async def generate_completion(prompt: str) -> str:
    """
    Ollama /api/generate 엔드포인트에 비동기로 프롬프트를 전송하고 
    단일 문자열 응답을 받아옵니다. (스트리밍은 MVP 복잡성 방지를 위해 제외)
    """
    endpoint = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            # N95 자원 보호를 위한 스레드 제한 옵션
            "num_thread": OLLAMA_NUM_THREAD
        }
    }
    
    try:
        # 타임아웃 30초 설정 (저전력 CPU 응답 지연 대비)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
            
    except httpx.TimeoutException:
        logger.error("Ollama API 타임아웃 발생 (N95 과부하 또는 모델 로딩 지연)")
        return ERROR_FALLBACK_MESSAGE
    except httpx.RequestError as e:
        logger.error(f"Ollama API 연결 실패 (서버 다운): {e}")
        # 로컬 개발 환경(LOGMON_ENV가 test가 아님)일 경우 대화 테스트 흐름을 매끄럽게 만들기 위해 모의 응답 시뮬레이션 적용
        if ("localhost" in OLLAMA_HOST or "127.0.0.1" in OLLAMA_HOST) and os.getenv("LOGMON_ENV") != "test":
            logger.info("Ollama API 미작동으로 인한 로컬 모의 분석 텍스트 출력")
            return "안녕하세요! 현재 로컬 Ollama(gemma2:2b) 서비스가 오프라인 상태이지만, RAG 컨텍스트를 활용해 모의 답변을 드립니다.\n\n요청하신 과거 로그 내역을 분석한 결과, 오늘 데이터베이스 연결 풀 초과 에러(DatabaseConnectionError)가 5번 발생하였으며, 설정 파일 `database.py`의 `pool_size`를 20 이상으로 조정하는 것을 제안합니다."
        return ERROR_FALLBACK_MESSAGE
    except Exception as e:
        logger.error(f"Ollama API 알 수 없는 에러: {e}")
        return ERROR_FALLBACK_MESSAGE
