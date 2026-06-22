# 🍏🪟 로그몬 (LogMon) 로컬 에이전트 배포 명세서 (Logmon-agent-specification.md)

이 문서는 로컬 개발 환경에서 IDE 사용 로그를 백그라운드에서 주기적으로 수집하여 서버로 전송하는 독립형 CLI 에이전트의 구동 및 배포 스펙을 정의합니다.

---

## ⚙️ 1. 에이전트 구동 매커니즘

1. **파이썬 환경 독립성**: 로컬 PC의 파이썬 설치 유무에 구애받지 않기 위해, 빌드 단계에서 `PyInstaller`를 통해 실행 파일 형태(macOS용 바이너리, Windows용 `exe`)로 패키징하여 배포합니다.
2. **중복 전송 방지 및 멱등성 보장 (Checkpoint)**:
   * 로컬 에이전트 실행 환경의 사용자 홈 디렉터리에 초경량 텍스트 파일인 `~/.logmon_checkpoint`를 생성합니다.
   * 이 파일에는 로그 파일의 마지막으로 읽은 **바이트 위치(Byte Offset)**를 기록합니다.
   * 5분 주기로 에이전트가 실행될 때, 이 체크포인트 파일의 오프셋 이후부터 새롭게 기록된 로그 데이터만 읽어 서버로 전송합니다.
   * **예외 처리**: 서버 전송 실패(네트워크 단절, 홈서버 다운 등) 시 오프셋을 갱신하지 않고 즉시 비정상 종료(또는 대기)하여 데이터 누락과 서버 측 중복 적재를 동시에 철저히 방지합니다.

---

## 🔒 2. 보안 필터 및 전송 API

에이전트는 수집한 로그를 전송할 때 반드시 최초 에이전트 설정 단계에서 발급된 유저 고유 API Key를 헤더에 주입하여 통신합니다.

* **전송 엔드포인트**: `POST http://[홈서버IP]/api/logmon/upload`
* **HTTP 헤더 설정**:
  * `Content-Type: application/json`
  * `X-LogMon-API-Key: [유저 API Key]`
* **백엔드 검증**: 백엔드는 헤더의 `X-LogMon-API-Key`를 수신하여 유효성을 검사한 뒤 정상인 경우에만 SQLite 및 Chroma DB 적재 파이프라인으로 넘겨줍니다.

---

## 📂 3. IDE 로그 파일 기본 탐색 경로

각 OS 환경별 Cursor IDE 로그 저장 경로는 아래와 같습니다. 에이전트는 기동 시 해당 디렉터리를 기본 스캔 대상으로 삼습니다.

* **macOS**: `~/Library/Application Support/Cursor/logs`
* **Windows**: `%APPDATA%\Cursor\logs`
* **Linux**: `~/.config/Cursor/logs`

---

## 🚀 4. OS별 스케줄러 동기화 설계 (5분 주기 배치)

에이전트가 개발 도중 백그라운드에서 조용히 활성화되도록 데몬/스케줄러 서비스를 등록합니다.

### 1) [🍏 macOS / Linux]
* **설치 스크립트**: `install-agent.sh`
* **동작 방식**: 
  * `/usr/local/bin/logmon-agent`에 바이너리를 다운로드 및 배치합니다. (또는 쉘 스크립트 구동 에이전트의 경우 `~/.logmon_agent/`에 파이썬 파일 배치)
  * macOS의 경우 `launchd` plist 등록(`~/Library/LaunchAgents/com.logmon.agent.plist`)을 하되, `agent_main.py`를 직접 기동하지 않고 **Wrapper 쉘 스크립트인 `run_agent.sh`**를 거쳐 실행하도록 구성합니다.
  * `run_agent.sh`는 `agent_main.py`가 에러 코드(비정상 종료)를 반환하면 5초 대기 후 최대 3회까지 재기동(심폐소생술)을 수행하며, 3회 모두 실패 시 최종 에러 코드를 반환하고 정상 종료 시에는 즉시 종료하여 자원을 반환합니다.
  * Linux의 경우 `cron` 서비스에 `*/5 * * * *` 스케줄을 추가하여 5분 주기 백그라운드 배치를 자동 가동시킵니다.
* **제거 스크립트**: `uninstall-agent.sh` (데몬/스케줄러 목록에서 삭제하고 바이너리, 스크립트 및 체크포인트 파일 제거).

### 2) [🪟 Windows]
* **설치 스크립트**: `install-agent.ps1` (PowerShell 관리자 권한 실행 요구)
* **동작 방식**:
  * `C:\Program Files\Logmon\` 디렉터리를 생성하고 바이너리 `logmon-agent.exe`를 다운로드하여 배치합니다.
  * 윈도우 **작업 스케줄러 (Task Scheduler)**에 새로운 작업으로 등록하여 `5분 간격으로 무한 반복` 및 `사용자 로그인 시 자동 시작` 트리거를 세팅합니다.
* **제거 스크립트**: `uninstall-agent.ps1` (작업 스케줄러에서 로그몬 작업 삭제 후 설치 디렉터리 및 체크포인트 제거).
