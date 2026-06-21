#!/usr/bin/env bash
set -e

echo "==============================================="
echo "  🧹 Logmon Agent 제거 마법사 (macOS/Linux)  "
echo "==============================================="
echo ""

OS_NAME=$(uname -s)

# 1. 스케줄러 중지 및 제거
if [ "$OS_NAME" = "Darwin" ]; then
    PLIST_PATH="$HOME/Library/LaunchAgents/com.logmon.agent.plist"
    if launchctl list | grep -q "com.logmon.agent"; then
        echo "🔄 macOS LaunchAgent(com.logmon.agent) 데몬을 중지합니다..."
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
    fi
    
    if [ -f "$PLIST_PATH" ]; then
        rm "$PLIST_PATH"
        echo "🗑️  PLIST 파일이 제거되었습니다."
    fi
    
elif [ "$OS_NAME" = "Linux" ]; then
    CRON_TEMP=$(mktemp)
    crontab -l | grep -v "agent_main.py" > "$CRON_TEMP" || true
    crontab "$CRON_TEMP"
    rm "$CRON_TEMP"
    echo "🗑️  Linux Crontab에서 스케줄 항목이 삭제되었습니다."
else
    echo "❌ 지원하지 않는 운영체제입니다: $OS_NAME"
    exit 1
fi

# 2. 백엔드에 제거 노티 전송 (UX 동기화용 메타 데이터)
CONFIG_FILE="$HOME/.logmon_config.json"
if [ -f "$CONFIG_FILE" ]; then
    B_URL=$(grep -o '"backend_url": *"[^"]*"' "$CONFIG_FILE" | cut -d'"' -f4)
    A_KEY=$(grep -o '"api_key": *"[^"]*"' "$CONFIG_FILE" | cut -d'"' -f4)
    if [ -n "$B_URL" ] && [ -n "$A_KEY" ]; then
        curl -s -X POST \
          -H "Content-Type: application/json" \
          -H "X-LogMon-API-Key: $A_KEY" \
          -d "{\"source_tool\": \"Agent CLI\", \"event_type\": \"AGENT_UNINSTALL\", \"raw_message\": \"Logmon 에이전트 제거 완료\"}" \
          "$B_URL/api/logmon/upload" >/dev/null || true
    fi
fi

# 3. 관련 설정 및 캐시 파일 클리어
CONFIG_FILE="$HOME/.logmon_config.json"
CHECKPOINT_FILE="$HOME/.logmon_checkpoint"
CRON_LOG="$HOME/.logmon_cron.log"

if [ -f "$CONFIG_FILE" ]; then
    rm "$CONFIG_FILE"
    echo "🗑️  설정 파일(.logmon_config.json) 삭제 완료."
fi

if [ -f "$CHECKPOINT_FILE" ]; then
    rm "$CHECKPOINT_FILE"
    echo "🗑️  수집 오프셋 캐시(.logmon_checkpoint) 삭제 완료."
fi

if [ -f "$CRON_LOG" ]; then
    rm "$CRON_LOG"
    echo "🗑️  Crontab 로그 파일 삭제 완료."
fi

# TODO (Phase 4): 바이너리 제거 로직
# if [ -f "/usr/local/bin/logmon-agent" ]; then
#     rm "/usr/local/bin/logmon-agent"
#     echo "🗑️  바이너리 삭제 완료."
# fi

echo ""
echo "✨ Logmon 에이전트가 시스템에서 완전히 제거되었습니다!"
