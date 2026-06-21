import os
import json
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# 에이전트 실행 환경의 현재 디렉터리 기준 또는 유저 홈 디렉터리
CHECKPOINT_FILE = os.path.expanduser("~/.logmon_checkpoint")

def _load_checkpoint_data() -> Dict[str, int]:
    try:
        if not os.path.exists(CHECKPOINT_FILE) or os.path.getsize(CHECKPOINT_FILE) == 0:
            return {}
    except OSError:
        return {}
        
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except json.JSONDecodeError:
        return {}
    except Exception as e:
        logger.warning(f"체크포인트 로드 중 에러 (초기화 진행): {e}")
        return {}

def _save_checkpoint_data(data: Dict[str, int]):
    try:
        # 멱등성 및 원자성 보장을 위해 임시 파일 기록 후 이름 변경하는 방식도 좋지만 
        # MVP 단계이므로 단일 쓰기로 구현합니다.
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"체크포인트 저장 중 에러: {e}")
        # 파일 권한 에러 등으로 저장이 안 될 경우, 다음 번 중복 전송이 일어날 수 있으므로 예외 발생
        raise

def get_last_offset(filepath: str) -> int:
    """
    특정 로그 파일의 이전에 스캔 완료된 바이트 오프셋(위치)을 반환합니다.
    """
    data = _load_checkpoint_data()
    return data.get(filepath, 0)

def update_offset(filepath: str, offset: int):
    """
    특정 로그 파일의 오프셋을 갱신합니다.
    (반드시 서버 전송이 성공적으로 끝난 이후에만 호출되어야 함)
    """
    data = _load_checkpoint_data()
    data[filepath] = offset
    _save_checkpoint_data(data)
    logger.debug(f"체크포인트 갱신 완료: {filepath} -> {offset} bytes")
