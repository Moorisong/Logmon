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
SSH_USER="shkim"                         # SSH 사용자 이름
SSH_HOST="your-home-server-ip"           # 홈서버 공인 IP 또는 도메인
SSH_PORT="22"                            # SSH 포트 (기본값: 22)
REMOTE_PROJECT_DIR="/path/to/Logmon"    # 홈서버 내 프로젝트 절대 경로
DEFAULT_COMMIT_MSG="deploy: auto-deploy update" # 기본 커밋 메시지
# --------------------------------------------------

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

# 변경 사항 유무 검증
if [ -z "$(git status --porcelain)" ]; then
    echo -e "${YELLOW}[안내] 커밋할 변경 사항이 없습니다. 배포 단계로 넘어갑니다.${NC}"
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

    echo -e "${BLUE}>>> 4. 원격 저장소 푸시 (${CURRENT_BRANCH})...${NC}"
    git push origin "$CURRENT_BRANCH"
    echo -e "${GREEN}[성공] 로컬 코드 원격 저장소 푸시 완료.${NC}"
fi

# SSH 접속 검증 및 정보 확인
if [ "$SSH_HOST" = "your-home-server-ip" ]; then
    echo -e "${YELLOW}[경고] deploy.sh 상단의 SSH 설정 정보가 수정되지 않았습니다.${NC}"
    echo -e "배포 스크립트를 사용하기 위해 홈서버 SSH 접속 주소 및 경로를 입력해주세요."
    read -p "홈서버 IP/도메인: " SSH_HOST
    read -p "홈서버 SSH 유저: " SSH_USER
    read -p "홈서버 내 프로젝트 절대 경로: " REMOTE_PROJECT_DIR
fi

echo -e "${BLUE}>>> 5. 홈서버 원격 접속 및 배포 업데이트 시작...${NC}"
echo -e "접속 대상: ${GREEN}${SSH_USER}@${SSH_HOST}:${SSH_PORT}${NC}"
echo -e "원격 경로: ${GREEN}${REMOTE_PROJECT_DIR}${NC}"

# SSH 명령어를 통해 원격 서버 제어
ssh -p "$SSH_PORT" "${SSH_USER}@${SSH_HOST}" << EOF
  set -e
  echo -e "\n=== 원격 서버 작업 시작 ==="
  
  # 1. 프로젝트 폴더로 이동
  if [ ! -d "${REMOTE_PROJECT_DIR}" ]; then
    echo -e "\e[31m[오류] 원격 프로젝트 경로가 존재하지 않습니다: ${REMOTE_PROJECT_DIR}\e[0m"
    exit 1
  fi
  cd "${REMOTE_PROJECT_DIR}"
  
  # 2. 최신 소스 pull
  echo -e "\e[34m[원격] Git Pull 실행 중... (브랜치: ${CURRENT_BRANCH})\e[0m"
  git fetch origin
  git checkout "${CURRENT_BRANCH}"
  git pull origin "${CURRENT_BRANCH}"
  
  # 3. Docker Compose 빌드 및 실행
  echo -e "\e[34m[원격] Docker Compose 빌드 및 무중단 재빌드 시작...\e[0m"
  docker compose up -d --build
  
  echo -e "\e[32m=== 원격 서버 배포 성공 완료 ===\e[0m\n"
EOF

echo -e "${GREEN}>>> 배포가 모두 완료되었습니다! ✨${NC}"
