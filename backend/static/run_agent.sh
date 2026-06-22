#!/usr/bin/env bash

# PYTHONPATH 및 기본 실행 경로 설정
AGENT_DIR="$HOME/.logmon_agent"
PYTHON_BIN=$(command -v python3 || command -v python)
AGENT_MAIN="$AGENT_DIR/agent_main.py"

export PYTHONPATH="$AGENT_DIR:$AGENT_DIR/.."

# 테스트 환경 변수 로그 출력
if [ "$LOGMON_ENV" = "test" ]; then
    echo "[TEST_MODE] LOGMON_ENV is set to test. Running with wrapper script."
fi

MAX_TRIES=3
TRY_COUNT=0
SUCCESS=false

while [ $TRY_COUNT -lt $MAX_TRIES ]; do
    TRY_COUNT=$((TRY_COUNT + 1))
    
    if [ "$LOGMON_ENV" = "test" ] || [ $TRY_COUNT -gt 1 ]; then
        echo "🔄 [Attempt $TRY_COUNT/$MAX_TRIES] Running agent..."
    fi
    
    # 파이썬 에이전트 실행
    "${PYTHON_BIN:-python3}" "$AGENT_MAIN"
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        SUCCESS=true
        if [ "$LOGMON_ENV" = "test" ]; then
            echo "✅ Agent executed successfully. Exit code: 0"
        fi
        break
    else
        echo "⚠️ Agent failed with exit code $EXIT_CODE."
        if [ $TRY_COUNT -lt $MAX_TRIES ]; then
            if [ "$LOGMON_ENV" = "test" ]; then
                echo "[TEST_MODE] Error detected. Waiting 5 seconds before retry..."
            fi
            sleep 5
        fi
    fi
done

if [ "$SUCCESS" = true ]; then
    exit 0
else
    echo "❌ Agent failed after $MAX_TRIES attempts."
    exit $EXIT_CODE
fi
