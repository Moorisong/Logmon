import os
import json
import urllib.request
import urllib.error
import logging

try:
  from agent.core.checkpoint import get_last_offset, update_offset
except ModuleNotFoundError:
  try:
    from core.checkpoint import get_last_offset, update_offset
  except ModuleNotFoundError:
    from checkpoint import get_last_offset, update_offset

logger = logging.getLogger(__name__)

def scan_and_send(filepath: str, backend_url: str, api_key: str):
    """
    타깃 로그 파일을 열어 마지막 체크포인트 이후의 신규 데이터를 읽은 후 백엔드로 전송합니다.
    전송이 성공했을 때만 체크포인트를 갱신합니다.
    """
    if not os.path.exists(filepath):
        logger.debug(f"파일이 존재하지 않습니다: {filepath}")
        return

    # 파일 락을 피하기 위해 단순 읽기('rb') 모드로 엽니다. 
    # (윈도우 환경에서도 대부분의 IDE는 'rb' 모드 스캔을 허용합니다)
    last_offset = get_last_offset(filepath)
    new_data_bytes = b""
    current_offset = last_offset

    try:
        with open(filepath, "rb") as f:
            # 파일 포인터를 마지막 오프셋으로 이동
            f.seek(last_offset)
            new_data_bytes = f.read()
            # 포인터의 마지막 위치(신규 오프셋)
            current_offset = f.tell()
    except Exception as e:
        logger.error(f"파일 읽기 실패 ({filepath}): {e}")
        return

    # 새로 추가된 내용이 없으면 중단
    if not new_data_bytes:
        return

    # 유저 스펙(2번 항목)에 따라 개별 라인 파싱 없이 통째로 텍스트로 디코딩
    try:
        raw_message = new_data_bytes.decode('utf-8', errors='replace')
    except Exception as e:
        logger.error(f"디코딩 에러 ({filepath}): {e}")
        return

    # 빈 텍스트면 패스
    if not raw_message.strip():
        # 쓰레기 값만 있어도 이미 읽은 것으로 간주해 오프셋 갱신
        update_offset(filepath, current_offset)
        return

    # 백엔드 전송 페이로드 구성
    # API 구조: POST /api/logmon/upload
    # 스펙상 event_type, source_tool 등은 Agent 단에서 고정하거나, 
    # 파일 경로 추적을 통해 일부 유추할 수 있으나 MVP에 맞게 기본값 부여
    payload = {
        "source_tool": "Cursor",
        "event_type": "LOG_DUMP",
        "raw_message": raw_message
    }
    
    base_url = backend_url.rstrip('/')
    if base_url.endswith('/api/logmon'):
        endpoint = f"{base_url}/upload"
    else:
        endpoint = f"{base_url}/api/logmon/upload"
    
    headers = {
        "Content-Type": "application/json",
        "X-LogMon-API-Key": api_key
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")

    try:
        # urllib를 이용한 타임아웃 10초 동기화 전송 (의존성 최소화)
        with urllib.request.urlopen(req, timeout=10.0) as response:
            status = response.getcode()
            if status in (200, 201):
                logger.info(f"전송 성공 ({status}): {filepath}")
                # [중요] 성공 시에만 오프셋 갱신 (멱등성 사수)
                update_offset(filepath, current_offset)
            else:
                logger.error(f"비정상 응답 ({status}). 오프셋 갱신 보류.")
    except urllib.error.HTTPError as e:
        # 401, 500 등의 에러 발생 시 예외 발생
        logger.error(f"HTTP 에러 발생 ({e.code}): {e.reason}")
    except urllib.error.URLError as e:
        # 서버 다운, DNS 등 네트워크 문제
        logger.error(f"네트워크 에러 발생: {e.reason}")
    except Exception as e:
        logger.error(f"알 수 없는 전송 에러 발생: {e}")
