#!/usr/bin/env node

const { execSync } = require('child_process');

const apiKey = process.env.API_KEY || "default_dev_key";
const backendUrl = "http://localhost:3008/api/logmon";

console.log('===============================================');
console.log('  👾 LogMon CLI 에이전트 무중단 설치기');
console.log('===============================================');

try {
  const installCmd = `export BACKEND_URL="${backendUrl}" && export API_KEY="${apiKey}" && curl -sL ${backendUrl}/static/install-agent.sh | bash`;
  execSync(installCmd, { stdio: 'inherit' });
} catch (error) {
  console.error('\n❌ 에이전트 설치 진행 중 실패:', error.message);
  process.exit(1);
}
