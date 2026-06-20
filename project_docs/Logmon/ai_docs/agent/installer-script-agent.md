# 🤖 installer-script-agent.md - AI 개발 가이드

이 문서는 macOS/Linux용 배시(Bash) 스크립트 및 Windows용 파워쉘(PowerShell) 설치/제거 스크립트 제작 및 시스템 데몬/작업 스케줄러 자동 등록을 위한 AI 에이전트용 설계 지침입니다.

---

## 📝 1. 연동 기획 명세 ([Logmon-agent-specification.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/agent/Logmon-agent-specification.md))
* **배포 채널**: FastAPI 백엔드 정적 서빙(`/api/logmon/static/`)을 통해 스크립트 노출.
* **macOS/Linux**: `launchd` 데몬 또는 `cron`에 `logmon-agent` 바이너리를 등록하여 5분 주기 배치 구동.
* **Windows**: PowerShell 기반으로 작업 스케줄러(Task Scheduler)에 등록하여 5분 주기로 백그라운드 구동.

---

## 🤖 2. AI 개발 지침 및 설계 구조

### 🎯 목적
* 복잡한 설치 단계 없이 터미널 한 줄 입력만으로 로컬 개발 PC에 컴파일된 에이전트 바이너리를 주입하고 백그라운드 스케줄러에 완벽 안착시키는 쉘 스크립트를 생성합니다.

### 📦 패키지 및 타깃 파일 목록
```plaintext
backend/
└── static/
    ├── install-agent.sh       # macOS/Linux 설치 자동화 스크립트
    ├── uninstall-agent.sh     # macOS/Linux 제거 스크립트
    ├── install-agent.ps1      # Windows PowerShell 설치 자동화 스크립트
    └── uninstall-agent.ps1    # Windows PowerShell 제거 스크립트
```

### 🛠️ 개발 단계 (Step-by-Step 상세 로직)

#### 1단계: macOS / Linux 설치 및 제거 스크립트 구현
* **`install-agent.sh`**:
  1. 시스템 아키텍처(Intel/Apple Silicon)를 판별하여 백엔드 서버로부터 그에 맞는 패키징 바이너리를 `/usr/local/bin/logmon-agent`에 다운로드합니다.
  2. 다운로드 완료 후 `chmod +x` 권한을 적용합니다.
  3. **스케줄러 등록**: macOS는 `~/Library/LaunchAgents/com.logmon.agent.plist`를 자동 생성하고 300초(5분) 주기로 바이너리가 구동되도록 `launchctl load`를 지시합니다. 리눅스 계열인 경우 사용자 `crontab`에 `*/5 * * * * /usr/local/bin/logmon-agent` 항목을 쉘을 통해 주입합니다.
* **`uninstall-agent.sh`**:
  1. `launchctl unload` 혹은 `crontab`에서 로그몬 스케줄 엔트리를 삭제합니다.
  2. 로컬 바이너리 및 생성되었던 `.logmon_checkpoint` 캐시 파일을 깨끗이 지웁니다.

#### 2단계: Windows PowerShell 설치 및 제거 스크립트 구현
* **`install-agent.ps1`**:
  1. 관리자 권한(`Administrator`)으로 구동 중인지 권한 레벨을 1차 체크합니다.
  2. `C:\Program Files\Logmon` 디렉터리를 만들고, 해당 디렉터리에 `logmon-agent.exe` 실행 바이너리를 백엔드에서 다운로드(iwr/Invoke-WebRequest)합니다.
  3. **작업 스케줄러 등록**: `Register-ScheduledTask` cmdlets를 사용하여, 5분 주기로 무한 반복 기동하며 로그인 상태 여부와 관계없이 실행되도록 트리거 및 동작 사양을 시스템에 등록합니다.
* **`uninstall-agent.ps1`**:
  1. `Unregister-ScheduledTask`를 호출하여 등록된 `LogmonAgentTask` 스케줄을 영구 격하합니다.
  2. `C:\Program Files\Logmon` 폴더 및 레지스트리 찌꺼기를 일체 수거 및 완전 삭제합니다.

---

## 🚨 3. 철벽 코드 컨벤션 및 제약 조건
* **[300줄 분리 규칙]**: 스크립트 내부에 과도한 파싱이나 거대한 로직을 포함하지 않고, 다운로드 ➡️ 배치 ➡️ 데몬 등록 3단계 핵심 태스크만 다루어 각각 **300줄** 이내로 슬림하게 유지하세요.
* **[멱등성 보장]**: 이미 설치 프로세스가 수행되어 데몬이 돌고 있는 상태에서 설치 스크립트가 재기동되더라도, 기존 스케줄러를 무조건 파괴하고 에러를 내는 것이 아니라 기존 프로세스를 정상 하차(Stop)시킨 후 깔끔하게 덮어쓰도록(Overwrite) 멱등성을 지키도록 제작하세요.
* **[네트워크 유연성]**: 백엔드 호스트 IP 주소를 스크립트 빌드 시 동적으로 템플릿 처리하거나 가변 인자(arguments)로 받아 설치할 수 있도록 파라미터 유연성을 지원하세요.
