#!/usr/bin/env bash
set -e

# 1. 환경 변수 검증 및 기본값 할당
CLI_VER="${CLI_VERSION:-v1.0.0}"
if [[ ! "$CLI_VER" =~ ^v ]]; then
    CLI_VER="v$CLI_VER"
fi

if [ -z "$BACKEND_URL" ]; then
    BACKEND_URL="https://logmon.haroo.site"
    echo "  > 서버 주소: $BACKEND_URL (기본값 설정)"
else
    echo "  > 서버 주소: $BACKEND_URL"
fi

if [ -z "$API_KEY" ]; then
    API_KEY="default_dev_key"
    echo "  > [경고] API Key가 제공되지 않아 기본 개발용 키($API_KEY)로 대체합니다."
else
    echo "  > 보안 인증: 매핑 완료! ✓"
fi
echo ""

# 2. 유저 홈 디렉터리에 독립 실행 환경 생성
AGENT_DIR="$HOME/.logmon_agent"
mkdir -p "$AGENT_DIR"

# 3. 설정 파일 생성 (격리 폴더 내부에 저장)
CONFIG_FILE="$AGENT_DIR/logmon_config.json"
cat > "$CONFIG_FILE" <<EOF
{
  "backend_url": "$BACKEND_URL",
  "api_key": "$API_KEY"
}
EOF

# 4. 백엔드 서버로부터 최신 agent_main.py 코드를 다운로드 (핵심 우회 로직)
AGENT_SCRIPT_PATH="$AGENT_DIR/agent_main.py"

# FastAPI 스태틱 경로 규칙에 맞게 소스 코드 다운로드 요청
curl -sL "$BACKEND_URL/static/agent_main.py" -o "$AGENT_SCRIPT_PATH"

# 정상적으로 다운로드 되었는지 검증 (404 Not Found 문자열 필터링)
if [ ! -f "$AGENT_SCRIPT_PATH" ] || grep -q "Not Found" "$AGENT_SCRIPT_PATH"; then
    echo "❌ 에이전트 스크립트 다운로드에 실패했습니다."
    echo "   백엔드 스태틱 폴더에 'agent_main.py' 파일이 복사되어 있는지 확인해 주세요."
    exit 1
fi
echo "✅ 설정 및 최신 에이전트 코드 동기화 완료! ✓"

# 5. 파이썬 바이너리 체크 및 실행 스펙 정의
PYTHON_BIN=$(command -v python3 || command -v python)
EXEC_CMD="$PYTHON_BIN"
EXEC_ARG1="$AGENT_SCRIPT_PATH"


# 6. OS 판별 및 스케줄러 등록
OS_NAME=$(uname -s)

if [ "$OS_NAME" = "Darwin" ]; then
    # macOS - launchd 등록
    PLIST_PATH="$HOME/Library/LaunchAgents/com.logmon.agent.plist"
    
    if launchctl list | grep -q "com.logmon.agent"; then
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
    fi
    
    mkdir -p "$HOME/Library/LaunchAgents"
    
    cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.logmon.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$EXEC_CMD</string>
        <string>$EXEC_ARG1</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>$AGENT_DIR</string>
    </dict>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF
    
    launchctl load "$PLIST_PATH"
    echo "🍎 macOS LaunchAgent 등록 완료 (5분 주기 실행)"
    
elif [ "$OS_NAME" = "Linux" ]; then
    # Linux - crontab 등록
    CRON_TEMP=$(mktemp)
    crontab -l | grep -v "agent_main.py" > "$CRON_TEMP" || true
    echo "*/5 * * * * cd $AGENT_DIR && export PYTHONPATH=$AGENT_DIR && $EXEC_CMD $EXEC_ARG1 >> $HOME/.logmon_cron.log 2>&1" >> "$CRON_TEMP"
    crontab "$CRON_TEMP"
    rm "$CRON_TEMP"
    echo "🐧 Linux Crontab 등록 완료 (5분 주기 실행)"
    
else
    echo "❌ 지원하지 않는 운영체제입니다: $OS_NAME"
    exit 1
fi

# 7. 설치 완료 로그 및 이스터 에그
echo ""
echo "🎉 Logmon 로컬 수집기 설치가 완료되었습니다!"
echo "   제거 명령어: curl -sL $BACKEND_URL/static/uninstall-agent.sh | bash"
echo ""
echo "      /\_/\   "
echo "    （｡･ω･｡)つ━☆・*。"
echo "    ⊂　   |  　　・゜+.  🐾 LogMon Agent is Watching You!"
echo "    　しーＪ　　　°。+ *´\`"
echo "==============================================="
echo "  [ System Build: $CLI_VER / Made by ksh💗 ]"
echo "==============================================="
echo ""