# LogMon

로그 데이터 분석 및 수동 업로드, 대시보드 시각화와 RAG 기반 챗 에이전트를 제공하는 모니터링 시스템입니다.

## 🚀 배포 자동화 가이드

로컬 환경에서 코드 수정 후 운영 서버(홈서버)에 일관된 빌드 환경을 한 번에 배포할 수 있도록 자동화 쉘 스크립트(`deploy.sh`)를 제공합니다.

### 1. 스크립트 설정
[deploy.sh](file:///Users/shkim/Desktop/Project/Logmon/deploy.sh) 파일 상단의 사용자 설정 영역을 홈서버 환경에 맞춰 입력합니다.
```bash
SSH_USER="shkim"                         # SSH 사용자 이름
SSH_HOST="your-home-server-ip"           # 홈서버 IP 혹은 도메인
SSH_PORT="22"                            # SSH 포트 (기본값: 22)
REMOTE_PROJECT_DIR="/path/to/Logmon"    # 홈서버 내 프로젝트 절대 경로
```

### 2. 배포 스크립트 실행
로컬 터미널에서 아래 명령을 실행하면 Git 변경 사항 커밋, 원격 푸시, 홈서버 Pull 및 Docker 빌드가 한 번에 진행됩니다.
```bash
./deploy.sh
```

### 3. Docker 빌드 캐시 무력화 배포 (선택)
도커 빌드 캐시 문제 등으로 인해 원격 서버에 변경 사항이 즉각 반영되지 않는 경우, `--no-cache` 옵션을 붙여서 이미지 빌드 캐시를 초기화하며 빌드하도록 할 수 있습니다.
```bash
./deploy.sh --no-cache
```

> [!NOTE]
> 스크립트 실행 시 커밋할 변경 사항이 없다면 Git 커밋 단계를 건너뛰고 홈서버 빌드 및 재배포 단계로 바로 진행됩니다.
