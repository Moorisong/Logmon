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
    타깃 로그 파일을 열어 마지막 체크포인트 이후의 신규 데이터를 최대 500KB 청크 단위로 나누어 백엔드로 전송합니다.
    """
    if not os.path.exists(filepath):
        logger.debug(f"파일이 존재하지 않습니다: {filepath}")
        return

    try:
        file_size = os.path.getsize(filepath)
    except Exception as e:
        logger.error(f"파일 크기 확인 실패 ({filepath}): {e}")
        return

    last_offset = get_last_offset(filepath)
    
    # 만약 파일이 로테이션되거나 새로 쓰여서 크기가 오프셋보다 작아진 경우
    if file_size < last_offset:
        last_offset = 0

    current_offset = last_offset
    MAX_READ_BYTES = 500 * 1024  # 한 번에 최대 500KB씩 읽어서 전송

    while current_offset < file_size:
        try:
            with open(filepath, "rb") as f:
                f.seek(current_offset)
                new_data_bytes = f.read(MAX_READ_BYTES)
                next_offset = f.tell()
        except Exception as e:
            logger.error(f"파일 읽기 실패 ({filepath}): {e}")
            break

        if not new_data_bytes:
            break

        try:
            raw_message = new_data_bytes.decode('utf-8', errors='replace')
        except Exception as e:
            logger.error(f"디코딩 에러 ({filepath}): {e}")
            break

        if not raw_message.strip():
            # 빈 메시지(공백만 있음)면 오프셋만 전진시키고 진행
            current_offset = next_offset
            update_offset(filepath, current_offset)
            continue

        # [수정됨] file_path 정보를 payload에 포함하여 백엔드로 전송
        payload = {
            "source_tool": "Cursor",
            "event_type": "LOG_DUMP",
            "raw_message": raw_message,
            "file_path": filepath
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
            # 10초 타임아웃
            with urllib.request.urlopen(req, timeout=10.0) as response:
                status = response.getcode()
                if status in (200, 201):
                    logger.info(f"전송 성공 ({status}): {filepath} (오프셋: {current_offset} -> {next_offset})")
                    current_offset = next_offset
                    update_offset(filepath, current_offset)
                else:
                    logger.error(f"비정상 응답 ({status})으로 중단. 오프셋 갱신 보류.")
                    break
        except urllib.error.HTTPError as e:
            logger.error(f"HTTP 에러 발생 ({e.code}): {e.reason} ({filepath})")
            break
        except urllib.error.URLError as e:
            logger.error(f"네트워크 에러 발생: {e.reason} ({filepath})")
            break
        except Exception as e:
            logger.error(f"알 수 없는 전송 에러 발생: {e} ({filepath})")
            break