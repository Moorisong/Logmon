#!/usr/bin/env node

const { execSync } = require('child_process');
const pkg = require('./package.json');

// argv[2]를 API Key로, argv[3]을 backendUrl로 파싱 (없으면 fallback 기본값 사용)
const apiKey = process.argv[2] || process.env.API_KEY || "default_dev_key";
const backendUrl = process.argv[3] || process.env.BACKEND_URL || "http://localhost:3008/api/logmon";

// 터미널 화면 보안 세척
process.stdout.write('\x1Bc');

console.log('===============================================');
console.log('  👾 LogMon CLI 에이전트 무중단 설치기');
console.log('===============================================');

try {
  const installCmd = `export BACKEND_URL="${backendUrl}" && export API_KEY="${apiKey}" && export CLI_VERSION="${pkg.version}" && curl -sL ${backendUrl}/static/install-agent.sh | bash`;
  execSync(installCmd, { stdio: 'inherit' });
} catch (error) {
  console.error('\n❌ 에이전트 설치 진행 중 실패:', error.message);
  process.exit(1);
}

