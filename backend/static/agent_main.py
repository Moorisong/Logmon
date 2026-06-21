import sys
import os
import logging
import traceback

# PYTHONPATH 또는 패키지 임포트 문제 해결을 위해 현재 파일이 속한 부모 디렉터리를 sys.path에 등록
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
  sys.path.insert(0, parent_dir)
if current_dir not in sys.path:
  sys.path.insert(0, current_dir)

try:
  from agent.config import load_config, get_ide_logs_dirs, get_target_log_files
  from agent.core.sender import scan_and_send
except ModuleNotFoundError:
  # 백엔드 스태틱 폴더 다운로드 시 등 단독 스펙 대비 로컬 대체 임포트 지원
  from config import load_config, get_ide_logs_dirs, get_target_log_files
  from core.sender import scan_and_send

# CLI 실행을 위한 기본 로깅 설정
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
  datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("agent_main")

def run():
  logger.info("Logmon Collector Agent 기동")
  
  # 1. 설정 로드
  config = load_config()
  backend_url = config.get("backend_url")
  api_key = config.get("api_key")
  
  if not backend_url or not api_key:
    logger.error("유효한 API Key가 없어 스캔을 중단합니다. 설정 파일을 확인해 주세요.")
    sys.exit(1)
    
  # 2. OS별 타깃 로그 디렉터리 스캔
  logs_dirs = get_ide_logs_dirs()
  if not logs_dirs:
    logger.info("스캔할 IDE 로그 디렉터리가 존재하지 않거나 발견되지 않았습니다.")
    sys.exit(0)
    
  target_files = get_target_log_files(logs_dirs)

  if not target_files:
    logger.info(f"스캔할 타깃 로그 파일이 없습니다: {logs_dirs}")
    sys.exit(0)
    
  logger.info(f"{len(target_files)}개의 로그 파일을 스캔합니다.")
  
  # 3. 각 파일별 오프셋 읽기 및 발송 파이프라인
  success_count = 0
  for filepath in target_files:
    try:
      scan_and_send(filepath, backend_url, api_key)
      success_count += 1
    except Exception as e:
      logger.error(f"파일 처리 중 치명적 에러 ({filepath}): {e}")
      logger.debug(traceback.format_exc())
      # 에러가 나더라도 다른 파일 스캔은 계속 진행함
      continue

  logger.info(f"에이전트 스캔 완료. (시도: {len(target_files)}, 오류 없는 호출: {success_count})")

    
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("사용자 인터럽트로 종료됩니다.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"에이전트 런타임 에러: {e}")
        sys.exit(1)
