#!/usr/bin/env node

const { execSync } = require('child_process');

// argv[2]를 API Key로, argv[3]을 backendUrl로 파싱 (없으면 fallback 기본값 사용)
const apiKey = process.argv[2] || process.env.API_KEY || "default_dev_key";
const backendUrl = process.argv[3] || process.env.BACKEND_URL || "http://localhost:3008/api/logmon";

// 터미널 화면 보안 세척
process.stdout.write('\x1Bc');


try {
  const installCmd = `export BACKEND_URL="${backendUrl}" && export API_KEY="${apiKey}" && curl -sL ${backendUrl}/static/install-agent.sh | bash`;
  execSync(installCmd, { stdio: 'inherit' });
} catch (error) {
  console.error('\n❌ 에이전트 설치 진행 중 실패:', error.message);
  process.exit(1);
}
