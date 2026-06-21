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
    ~/.logmon_config.json 또는 ~/.logmon_agent/logmon_config.json 에서 환경설정 정보를 로드합니다.
    """
    config_path = CONFIG_FILE_PATH
    if not os.path.exists(config_path):
        alt_path = os.path.expanduser("~/.logmon_agent/logmon_config.json")
        if os.path.exists(alt_path):
            config_path = alt_path
            
    if not os.path.exists(config_path):
        logger.warning(
            f"설정 파일을 찾을 수 없습니다: {CONFIG_FILE_PATH} 또는 {alt_path if 'alt_path' in locals() else ''}\n"
            f"터미널에서 먼저 다음 형식으로 홈 디렉터리에 파일을 생성해주세요:\n"
            f'{{\n  "backend_url": "{DEFAULT_BACKEND_URL}",\n  "api_key": "YOUR_SECURE_API_KEY"\n}}\n'
            f"현재 테스트용 기본값({DEFAULT_BACKEND_URL})으로 동작을 시도합니다. "
            f"API Key가 없으면 서버에서 거절될 수 있습니다."
        )
        return {"backend_url": DEFAULT_BACKEND_URL, "api_key": ""}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        backend_url = data.get("backend_url", DEFAULT_BACKEND_URL)
        api_key = data.get("api_key", "")
        
        if not api_key:
            logger.warning("config.json 내에 'api_key'가 비어있습니다. 백엔드에서 인증 거부될 수 있습니다.")
            
        return {"backend_url": backend_url, "api_key": api_key}
    except Exception as e:
        logger.error(f"설정 파일 파싱 중 에러 발생: {e}")
        return {"backend_url": DEFAULT_BACKEND_URL, "api_key": ""}

def get_ide_logs_dirs() -> List[str]:
  """
  OS 플랫폼을 판별하여 Cursor 및 Antigravity IDE 기본 로그 디렉터리 경로 목록을 반환합니다.
  """
  system = platform.system()
  dirs = []
  home = os.path.expanduser("~")
  
  if system == "Darwin": # macOS
    dirs.append(os.path.join(home, "Library/Application Support/Cursor/logs"))
    dirs.append(os.path.join(home, "Library/Application Support/Antigravity/logs"))
    dirs.append(os.path.join(home, "Library/Application Support/Antigravity IDE/logs"))
  elif system == "Windows":
    appdata = os.getenv("APPDATA", "")
    if appdata:
      dirs.append(os.path.join(appdata, "Cursor/logs"))
      dirs.append(os.path.join(appdata, "Antigravity/logs"))
      dirs.append(os.path.join(appdata, "Antigravity IDE/logs"))
  elif system == "Linux":
    dirs.append(os.path.join(home, ".config/Cursor/logs"))
    dirs.append(os.path.join(home, ".config/Antigravity/logs"))
    dirs.append(os.path.join(home, ".config/Antigravity IDE/logs"))
  else:
    logger.warning(f"지원하지 않는 OS입니다: {system}")
    
  return [d for d in dirs if os.path.exists(d)]

def get_target_log_files(logs_dirs: List[str]) -> List[str]:
  """
  주어진 로그 디렉터리 목록 내에서 확장자가 .log인 파일 목록을 반환합니다.
  """
  target_files = []
  for logs_dir in logs_dirs:
    if not logs_dir or not os.path.exists(logs_dir):
      continue
    # 하위 디렉토리를 포함하여 .log 확장자를 가진 파일 스캔
    for root, _, files in os.walk(logs_dir):
      for file in files:
        if file.endswith(".log"):
          target_files.append(os.path.join(root, file))
          
  return target_files

