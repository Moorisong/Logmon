import os
import sys
import json
import platform
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

CONFIG_FILE_PATH = os.path.expanduser("~/.logmon_config.json")
DEFAULT_BACKEND_URL = "http://localhost:8000"

def load_config() -> Dict[str, str]:
    """
    ~/.logmon_config.json 에서 환경설정 정보를 로드합니다.
    파일이 없거나 API Key가 누락된 경우 기본값(Fallback)과 함께 안내 메시지를 출력합니다.
    """
    if not os.path.exists(CONFIG_FILE_PATH):
        logger.warning(
            f"설정 파일을 찾을 수 없습니다: {CONFIG_FILE_PATH}\n"
            f"터미널에서 먼저 다음 형식으로 홈 디렉터리에 파일을 생성해주세요:\n"
            f'{{\n  "backend_url": "{DEFAULT_BACKEND_URL}",\n  "api_key": "YOUR_SECURE_API_KEY"\n}}\n'
            f"현재 테스트용 기본값({DEFAULT_BACKEND_URL})으로 동작을 시도합니다. "
            f"API Key가 없으면 서버에서 거절될 수 있습니다."
        )
        return {"backend_url": DEFAULT_BACKEND_URL, "api_key": ""}

    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        backend_url = data.get("backend_url", DEFAULT_BACKEND_URL)
        api_key = data.get("api_key", "")
        
        if not api_key:
            logger.warning("config.json 내에 'api_key'가 비어있습니다. 백엔드에서 인증 거부될 수 있습니다.")
            
        return {"backend_url": backend_url, "api_key": api_key}
    except Exception as e:
        logger.error(f"설정 파일 파싱 중 에러 발생: {e}")
        return {"backend_url": DEFAULT_BACKEND_URL, "api_key": ""}

def get_cursor_logs_dir() -> str:
    """
    OS 플랫폼을 판별하여 Cursor IDE 기본 로그 디렉터리 경로를 반환합니다.
    """
    system = platform.system()
    if system == "Darwin": # macOS
        return os.path.expanduser("~/Library/Application Support/Cursor/logs")
    elif system == "Windows":
        return os.path.expandvars(r"%APPDATA%\Cursor\logs")
    elif system == "Linux":
        return os.path.expanduser("~/.config/Cursor/logs")
    else:
        logger.warning(f"지원하지 않는 OS입니다: {system}")
        return ""

def get_target_log_files(logs_dir: str) -> List[str]:
    """
    주어진 로그 디렉터리 내에서 확장자가 .log인 파일 목록을 반환합니다.
    이 MVP 단계에서는 폴더 내부를 재귀 탐색하거나, 
    수정 시간이 최근인 파일들을 위주로 가져올 수 있습니다.
    """
    target_files = []
    if not logs_dir or not os.path.exists(logs_dir):
        logger.debug(f"로그 디렉토리가 존재하지 않습니다: {logs_dir}")
        return target_files

    # 하위 디렉토리를 포함하여 .log 확장자를 가진 파일 스캔
    for root, _, files in os.walk(logs_dir):
        for file in files:
            if file.endswith(".log"):
                target_files.append(os.path.join(root, file))
                
    return target_files
