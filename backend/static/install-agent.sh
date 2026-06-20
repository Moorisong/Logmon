#!/usr/bin/env bash
set -e

echo "==============================================="
echo "  🚀 Logmon Agent 설치 마법사 (macOS/Linux)  "
echo "==============================================="
echo ""

# 1. 대화형 설정 입력
read -p "백엔드 서버 주소를 입력하세요 (예: https://logmon.haroo.site): " BACKEND_URL
if [ -z "$BACKEND_URL" ]; then
    BACKEND_URL="https://logmon.haroo.site"
    echo "  > 입력이 없어 기본값($BACKEND_URL)으로 설정합니다."
fi

read -p "발급받은 보안 API Key를 입력하세요: " API_KEY
if [ -z "$API_KEY" ]; then
    echo "  > [경고] API Key가 비어있습니다. 백엔드 전송이 거부될 수 있습니다."
fi

# 2. 설정 파일 생성
CONFIG_FILE="$HOME/.logmon_config.json"
cat > "$CONFIG_FILE" <<EOF
{
  "backend_url": "$BACKEND_URL",
  "api_key": "$API_KEY"
}
EOF
echo "✅ 설정 파일이 저장되었습니다: $CONFIG_FILE"

# 3. MVP용 바이너리 경로 우회 셋업
# TODO (Phase 4): 추후 curl 다운로드 방식으로 교체할 포인트
# curl -sL "$BACKEND_URL/api/logmon/static/logmon-agent-mac" -o /usr/local/bin/logmon-agent
# chmod +x /usr/local/bin/logmon-agent
# EXEC_CMD="/usr/local/bin/logmon-agent"

# MVP 단계: 현재 프로젝트의 파이썬 인터프리터 및 agent_main.py 경로 매핑
PYTHON_BIN=$(command -v python3 || command -v python)
CURRENT_DIR=$(pwd)
# 설치 스크립트가 밖에서 실행될 수 있으므로, 상위 Logmon 폴더를 추적 (만약 못 찾으면 홈 디렉터리 기준 매핑 등)
# MVP 환경에서는 이 스크립트를 Logmon 루트 폴더에서 실행한다고 가정
AGENT_SCRIPT_PATH="$CURRENT_DIR/agent/agent_main.py"
EXEC_CMD="$PYTHON_BIN"
EXEC_ARG1="$AGENT_SCRIPT_PATH"

if [ ! -f "$AGENT_SCRIPT_PATH" ]; then
    echo "❌ 현재 위치에서 agent/agent_main.py를 찾을 수 없습니다."
    echo "   Logmon 프로젝트 최상단 디렉터리에서 스크립트를 실행해 주세요."
    exit 1
fi

echo "✅ 에이전트 실행 환경 매핑 완료: $EXEC_CMD $EXEC_ARG1"

# 4. OS 판별 및 스케줄러 등록
OS_NAME=$(uname -s)

if [ "$OS_NAME" = "Darwin" ]; then
    # macOS - launchd 등록
    PLIST_PATH="$HOME/Library/LaunchAgents/com.logmon.agent.plist"
    
    # 멱등성: 기존 스케줄러 존재 시 하차(Unload)
    if launchctl list | grep -q "com.logmon.agent"; then
        echo "🔄 기존 데몬을 중지하고 업데이트합니다..."
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
        <string>$CURRENT_DIR</string>
    </dict>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF
    
    launchctl load "$PLIST_PATH"
    echo "🍎 macOS LaunchAgent(com.logmon.agent) 등록 완료. (5분 주기 실행)"
    
elif [ "$OS_NAME" = "Linux" ]; then
    # Linux - crontab 등록
    # 멱등성: 기존 logmon-agent 크론 지우고 덧붙이기
    CRON_TEMP=$(mktemp)
    crontab -l | grep -v "agent_main.py" > "$CRON_TEMP" || true
    # PYTHONPATH 주입 후 실행 (cron 환경 변수 한계 극복)
    echo "*/5 * * * * cd $CURRENT_DIR && export PYTHONPATH=$CURRENT_DIR && $EXEC_CMD $EXEC_ARG1 >> $HOME/.logmon_cron.log 2>&1" >> "$CRON_TEMP"
    crontab "$CRON_TEMP"
    rm "$CRON_TEMP"
    echo "🐧 Linux Crontab 등록 완료. (5분 주기 실행)"
    
else
    echo "❌ 지원하지 않는 운영체제입니다: $OS_NAME"
    exit 1
fi

echo ""
echo "🎉 Logmon 로컬 수집기 설치가 완료되었습니다!"
echo "   백그라운드에서 매 5분마다 IDE 로그를 체크하여 서버로 전송합니다."
echo "   제거를 원하시면 uninstall-agent.sh 를 실행하세요."
