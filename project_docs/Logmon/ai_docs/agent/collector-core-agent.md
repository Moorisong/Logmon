# 🤖 collector-core-agent.md - AI 개발 가이드

이 문서는 로컬 개발 PC의 백그라운드에서 주기적으로 IDE 사용 로그를 스캔하여 체크포인트를 관리하고 파싱 데이터를 전송하는 CLI 수집 에이전트 구축을 위한 AI 에이전트용 설계 지침입니다.

---

## 📝 1. 연동 기획 명세 ([Logmon-agent-specification.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/agent/Logmon-agent-specification.md))
* **보안 헤더**: `X-LogMon-API-Key`를 실어 HTTP 요청을 발송해야 함.
* **동작 방식**: 5분 주기 배치 스케줄러에 최적화된 독립 프로세스로 단일 기동 후 즉시 종료하는 구조.
* **데이터 무결성**: `.logmon_checkpoint` 오프셋 관리를 활용해 중복 및 유실 완전 방어.

---

## 🤖 2. AI 개발 지침 및 설계 구조

### 🎯 목적
* 가볍고 의존성 없는 로컬용 실행 바이너리 형태를 띠며, Cursor 및 IDE의 최신 로그 데이터만 정확히 조준하여 읽어낸 뒤 백엔드로 안전하게 업로드합니다.

### 📦 패키지 및 타깃 클래스 경로 구조
```plaintext
agent/
├── agent_main.py              # CLI 수집 에이전트 실행부 진입점
├── core/
│   ├── checkpoint.py          # 체크포인트 오프셋(Byte Offset) 관리자
│   └── sender.py              # X-LogMon-API-Key 헤더 기반 HTTP API 발송기
└── config.py                  # API Key 로드 및 OS별 Cursor 로그 경로 탐색
```

### 🛠️ 개발 단계 (Step-by-Step 상세 로직)

#### 1단계: OS별 기본 로그 디렉터리 탐색 및 타깃 파일 스캔
* `config.py` 파일 내에서 Python `platform` 라이브러리로 OS를 판별하여 기본 Cursor 로그 디렉터리를 조준합니다.
* 해당 디렉터리 하위에 있는 `.log` 파일 중 수정 날짜가 가장 최근이거나 활성화 상태인 파일들을 타깃 파일 목록으로 가져옵니다.

#### 2단계: 체크포인트 오프셋 제어 (`checkpoint.py`)
* 중복 읽기와 재전송을 완벽히 통제하기 위해 바이트 오프셋 방식의 체크포인트를 작동시킵니다.
```python
import os

CHECKPOINT_FILE = ".logmon_checkpoint"

def get_last_offset(filepath: str) -> int:
    if not os.path.exists(CHECKPOINT_FILE):
        return 0
    # 체크포인트 파일에서 특정 로그 파일 경로에 매핑된 바이트 오프셋 반환
    # 예: "filepath:offset" 또는 JSON 구조
    return parse_checkpoint_offset(CHECKPOINT_FILE, filepath)

def update_offset(filepath: str, offset: int):
    # 전송이 성공한 경우에만 호출되어 체크포인트를 갱신함
    write_checkpoint_offset(CHECKPOINT_FILE, filepath, offset)
```

#### 3단계: 부분 로그 리딩 및 전송 (`sender.py`)
1. 에이전트 기동 시 타깃 파일의 크기(size)를 구하고, 체크포인트 오프셋 위치를 비교합니다.
2. 오프셋 위치로 `seek()` 이동한 뒤, 추가된 신규 데이터만 읽어 메모리에 올립니다.
3. 읽어낸 로그 페이로드를 담아 `sender.py` 모듈을 통해 `POST /api/logmon/upload`로 발송합니다.
4. 이때 헤더에 `X-LogMon-API-Key`를 필수 주입합니다.
5. **예외 및 멱등성 사수**: HTTP 전송 실패 및 타임아웃 발생 시 오프셋을 갱신하는 `update_offset` 함수를 **절대로 호출하지 않고 비정상 종료(또는 예외 발생)** 처리하여, 다음 5분 루프 기동 시 해당 오프셋부터 재스캔을 시도하게 만듭니다.

---

## 🚨 3. 철벽 코드 컨벤션 및 제약 조건
* **[300줄 분리 규칙]**: 가벼운 CLI 에이전트라 할지라도 `agent_main.py`에 모든 로직을 적지 말고, 체크포인트 제어, HTTP 발송부 등을 모듈화하여 단일 파일 300줄 한계를 사수하세요.
* **[의존성 다이어트]**: PyInstaller로 패키징할 때 바이너리 용량이 과도하게 커지는 것을 막기 위해 `requests` 대신 표준 라이브러리 `urllib.request`를 사용하거나, 사용하지 않는 패키지는 임포트 목록에서 완전히 지우세요.
* **[로컬 파일 잠금 우회]**: IDE가 실행되는 동안 실시간으로 로그를 작성하며 파일을 쥐고 있을 수 있으므로, 에이전트가 읽을 때 공유 읽기 모드(`r` 또는 OS에 특화된 open 플래그)로 열어서 파일 잠금 에러를 우회해야 합니다.
