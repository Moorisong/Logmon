#!/bin/bash

# ==============================================================================
# LogMon 원스톱 배포 자동화 스크립트 (deploy.sh)
# ==============================================================================
# [기능 요약]
# 1. 로컬 코드 변경 사항을 커밋하고 Git 원격 저장소(GitHub)로 푸시합니다.
# 2. SSH로 홈서버(운영 환경)에 접속하여 최신 소스를 Pull 받습니다.
# 3. 홈서버 환경에 맞춰 Docker Compose 컨테이너를 재빌드 및 재시작합니다.
# ==============================================================================

# --- 사용자 설정 영역 (홈서버 환경에 맞춰 수정하세요) ---
SSH_USER="ksh"                            # SSH 사용자 이름
SSH_HOST_INT="192.168.0.6"               # 홈서버 내부 IP
SSH_HOST_EXT="125.190.25.48"             # 홈서버 외부 공인 IP
SSH_PORT="8193"                          # SSH 포트
REMOTE_PROJECT_DIR="/home/ksh/logmon"      # 홈서버 내 프로젝트 절대 경로
DEFAULT_COMMIT_MSG="deploy: auto-deploy update" # 기본 커밋 메시지
# --------------------------------------------------

# 인자 확인 (도커 캐시 무력화 옵션)
NO_CACHE_FLAG=""
for arg in "$@"; do
    if [ "$arg" == "--no-cache" ]; then
        NO_CACHE_FLAG="--no-cache"
    fi
done

set -e # 에러 발생 시 즉시 실행 중단


# 색상 정의
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}>>> 1. 현재 Git 브랜치 정보 확인 중...${NC}"
CURRENT_BRANCH=$(git symbolic-ref --short -q HEAD)
if [ -z "$CURRENT_BRANCH" ]; then
    echo -e "${RED}[오류] 현재 Git 브랜치 명을 감지할 수 없습니다. Git 초기화 여부를 확인하세요.${NC}"
    exit 1
fi
echo -e "현재 브랜치: ${GREEN}${CURRENT_BRANCH}${NC}"

echo -e "${BLUE}>>> 2. Git 변경 사항 점검...${NC}"
git status --short

# 변경 사항 유무 검증 및 커밋
if [ -z "$(git status --porcelain)" ]; then
    echo -e "${YELLOW}[안내] 커밋할 변경 사항이 없습니다.${NC}"
else
    # 변경된 파일들을 바탕으로 커밋 메시지를 적당히 자동 구성합니다.
    CHANGED_FILES=$(git diff --name-only | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')
    if [ -n "$CHANGED_FILES" ]; then
        COMMIT_MSG="deploy: update $CHANGED_FILES"
    else
        COMMIT_MSG="$DEFAULT_COMMIT_MSG"
    fi
    # 메시지가 지나치게 길어지면 잘라냅니다.
    if [ ${#COMMIT_MSG} -gt 100 ]; then
        COMMIT_MSG="${COMMIT_MSG:0:97}..."
    fi
    echo -e "자동 구성된 커밋 메시지: ${GREEN}\"${COMMIT_MSG}\"${NC}"

    echo -e "${BLUE}>>> 3. Git 스테이징 및 커밋 진행...${NC}"
    git add .
    git commit -m "$COMMIT_MSG"
fi

echo -e "${BLUE}>>> 4. 원격 저장소 푸시 (${CURRENT_BRANCH})...${NC}"
git push origin "$CURRENT_BRANCH"
echo -e "${GREEN}[성공] 로컬 코드 원격 저장소 푸시 완료.${NC}"

# SSH 접속 호자동 판별 (내부망 우선 접속 체크)
echo -e "${BLUE}>>> 5. 홈서버 SSH 접속 가능 여부 체크 중...${NC}"
if python3 -c "import socket; s = socket.socket(); s.settimeout(2); s.connect(('$SSH_HOST_INT', $SSH_PORT))" 2>/dev/null; then
    SSH_HOST="$SSH_HOST_INT"
    echo -e "접속 경로: ${GREEN}내부망 (인프라 내부 직접 연결: ${SSH_HOST})${NC}"
else
    SSH_HOST="$SSH_HOST_EXT"
    echo -e "접속 경로: ${YELLOW}외부망 (공인 IP 우회 연결: ${SSH_HOST})${NC}"
fi

echo -e "${BLUE}>>> 6. 홈서버 원격 접속 및 배포 업데이트 시작...${NC}"
echo -e "접속 대상: ${GREEN}${SSH_USER}@${SSH_HOST}:${SSH_PORT}${NC}"

# SSH 명령어를 통해 원격 서버 제어
ssh -o ConnectTimeout=5 -p "$SSH_PORT" "${SSH_USER}@${SSH_HOST}" << EOF
  set -e
  echo -e "\n=== 원격 서버 작업 시작 ==="
  
  # 프로젝트 폴더 탐색 및 이동
  TARGET_DIR="${REMOTE_PROJECT_DIR}"
  if [ ! -d "\$TARGET_DIR" ]; then
    for alt in "/home/${SSH_USER}/logmon" "/home/${SSH_USER}/Logmon" "/home/${SSH_USER}/Desktop/Project/Logmon" "/home/${SSH_USER}/Project/Logmon" "\$HOME/logmon" "\$HOME/Logmon"; do
      if [ -d "\$alt" ]; then
        TARGET_DIR="\$alt"
        break
      fi
    done
  fi

  if [ ! -d "\$TARGET_DIR" ]; then
    echo -e "\e[31m[오류] 원격 프로젝트 경로를 찾을 수 없습니다.\e[0m"
    exit 1
  fi

  echo -e "배포 대상 원격 경로: \e[32m\$TARGET_DIR\e[0m"
  cd "\$TARGET_DIR"
  
  # 1. 최신 소스 pull 선행 (도커 컴포즈 리스타트 명령어 구동을 위해)
  echo -e "\e[34m[원격] Git Pull 실행 중... (브랜치: ${CURRENT_BRANCH})\e[0m"
  git fetch origin
  git checkout "${CURRENT_BRANCH}"
  
  if [ -f "backend/db/logmon.db" ] && ! git ls-files --error-unmatch backend/db/logmon.db >/dev/null 2>&1; then
    mv backend/db/logmon.db "backend/db/logmon.db.bak_\$(date +%Y%m%d_%H%M%S)" || true
  fi
  git pull origin "${CURRENT_BRANCH}"

  # Ollama 11434 포트 헬스체크 및 도커 컨테이너 강제 심폐소생술
  echo -e "\e[34m[원격] Ollama 헬스체크 및 도커 컨테이너 검사 중...\e[0m"
  PORT_ACTIVE=false
  if nc -z localhost 11434 2>/dev/null; then
    PORT_ACTIVE=true
  fi

  API_RESPONSE=0
  if [ "\$PORT_ACTIVE" = true ]; then
    API_RESPONSE=\$(curl -s -o /dev/null -w "%{http_code}" http://localhost:11434/api/tags || echo "000")
  fi

  if [ "\$PORT_ACTIVE" = false ] || [ "\$API_RESPONSE" != "200" ]; then
    echo -e "\e[33m[원격] [경고] 도커 내부 Ollama 서비스 찐빠 감지 (포트: \$PORT_ACTIVE, 응답: \$API_RESPONSE). 컨테이너 강제 리스타트 슛!\e[0m"
    
    # 호스트 systemctl 뇌절 제거, 실제 도커 컴포즈 내 Ollama 서비스 타격
    docker compose restart logmon-ollama 2>/dev/null || docker compose up -d logmon-ollama
    
    echo -e "\e[34m[원격] Ollama 컨테이너 200 OK 응답 대기 중 (최대 45초)... \e[0m"
    for i in {1..15}; do
      HEALTH_CODE=\$(curl -s -o /dev/null -w "%{http_code}" http://localhost:11434/api/tags || echo "000")
      if [ "\$HEALTH_CODE" = "200" ]; then
        echo -e "\e[32m[원격] Ollama 컨테이너 헬스체크 성공! (API 응답 코드: 200)\e[0m"
        break
      fi
      echo -e "\e[33m[원격] 컨테이너 안정화 대기 중 (\${i}/15)... \e[0m"
      sleep 3
    done
  else
    echo -e "\e[32m[원격] Ollama 컨테이너 정상 가동 중 (API 응답 코드: 200)\e[0m"
  fi
  
  # 3. Docker Compose 빌드 및 실행
  echo -e "\e[34m[원격] Docker Compose 백엔드/UI 빌드 및 무중단 재빌드 시작...\e[0m"
  if [ -n "$NO_CACHE_FLAG" ]; then
    docker compose build --no-cache && docker compose up -d
  else
    docker compose up -d --build
  fi
  
  echo -e "\e[32m=== 원격 서버 배포 성공 완료 ===\e[0m\n"
EOF

echo -e "${GREEN}>>> 배포가 모두 완료되었습니다! ✨${NC}"