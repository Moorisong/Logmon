#!/usr/bin/env node

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');
const readline = require('readline');
const pkg = require('./package.json');

// 전체 인자 중 'uninstall'이 포함되어 있는지 견고하게 확인
const isUninstall = process.argv.includes('uninstall');

function getSavedConfig() {
  const homeDir = os.homedir();
  const unixConfigPath = path.join(homeDir, '.logmon_agent', 'logmon_config.json');
  const winConfigPath = path.join(homeDir, '.logmon_config.json');

  if (fs.existsSync(unixConfigPath)) {
    try {
      return JSON.parse(fs.readFileSync(unixConfigPath, 'utf8'));
    } catch (e) {}
  }
  if (fs.existsSync(winConfigPath)) {
    try {
      return JSON.parse(fs.readFileSync(winConfigPath, 'utf8'));
    } catch (e) {}
  }
  return null;
}

function askQuestion(query) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => rl.question(query, (ans) => {
    rl.close();
    resolve(ans);
  }));
}

async function run() {
  // 버전 확인 파라미터 체크
  const isVersion = process.argv.includes('--version') || process.argv.includes('-v') || process.argv.includes('version');
  if (isVersion) {
    console.log(`logmon v${pkg.version}`);
    process.exit(0);
  }

  let apiKey = "default_dev_key";
  let backendUrl = "http://localhost:3008/api/logmon";

  // 기존 저장된 설정 시도
  const savedConfig = getSavedConfig();
  if (savedConfig) {
    if (savedConfig.api_key) apiKey = savedConfig.api_key;
    if (savedConfig.backend_url) backendUrl = savedConfig.backend_url;
  }

  // HTTP/HTTPS 프로토콜로 시작하는 인자 검색
  const foundUrl = process.argv.find(arg => arg.startsWith('http://') || arg.startsWith('https://'));

  if (isUninstall) {
    backendUrl = foundUrl || process.env.BACKEND_URL || backendUrl;
  } else {
    // 설치 시
    const firstArg = process.argv[2];
    if (firstArg && !firstArg.startsWith('http://') && !firstArg.startsWith('https://') && firstArg !== 'uninstall') {
      apiKey = firstArg;
    } else {
      apiKey = process.env.API_KEY || apiKey;
    }
    backendUrl = foundUrl || process.env.BACKEND_URL || backendUrl;

    // 만약 기존 설정도 없고, 인자도 주어지지 않았고, 테스트 모드가 아닐 때 대화형 입력 받기
    if (!savedConfig && !foundUrl && (!firstArg || firstArg === 'uninstall') && process.env.LOGMON_TEST_MODE !== 'true') {
      console.log('===============================================');
      console.log('  ⚙️  LogMon CLI 초기 설정');
      console.log('===============================================');
      const inputUrl = await askQuestion(`백엔드 서버 주소 [${backendUrl}]: `);
      if (inputUrl.trim()) {
        backendUrl = inputUrl.trim();
      }
      const inputKey = await askQuestion(`보안 API Key [${apiKey}]: `);
      if (inputKey.trim()) {
        apiKey = inputKey.trim();
      }
    }
  }

  // 터미널 화면 보안 세척
  process.stdout.write('\x1Bc');

  // 설치인 경우에만 상단 타이틀을 띄워 중복 방지
  if (!isUninstall) {
    console.log('===============================================');
    console.log('  👾 LogMon CLI 에이전트 무중단 설치기');
    console.log('===============================================');
  }

  try {
    if (isUninstall) {
      const uninstallCmd = `export BACKEND_URL="${backendUrl}" && curl -sL ${backendUrl}/static/uninstall-agent.sh | bash`;
      if (process.env.LOGMON_TEST_MODE === 'true') {
        console.log('===============================================');
        console.log('  🧹 Logmon Agent 제거 마법사 (macOS/Linux)  ');
        console.log('===============================================');
        console.log('\n🔄 macOS LaunchAgent(com.logmon.agent) 데몬을 중지합니다...');
        console.log('🗑️  PLIST 파일이 제거되었습니다.');
        console.log('\n✨ Logmon 에이전트가 시스템에서 완전히 제거되었습니다!');
      } else {
        execSync(uninstallCmd, { stdio: 'inherit' });
      }
    } else {
      const installCmd = `export BACKEND_URL="${backendUrl}" && export API_KEY="${apiKey}" && export CLI_VERSION="${pkg.version}" && curl -sL ${backendUrl}/static/install-agent.sh | bash`;
      if (process.env.LOGMON_TEST_MODE === 'true') {
        console.log(`  > 서버 주소: ${backendUrl}`);
        console.log('  > 보안 인증: 매핑 완료! ✓\n');
        console.log('✅ 설정 및 최신 에이전트 코드 동기화 완료! ✓');
        console.log('🍎 macOS LaunchAgent 등록 완료 (5분 주기 실행)');
      } else {
        execSync(installCmd, { stdio: 'inherit' });
      }
      
      console.log('\n🎉 Logmon 로컬 수집기 설치가 완료되었습니다!');
      console.log(`   제거 명령어: npx logmon-cli uninstall\n`);
      console.log('      /\\_/\\   ');
      console.log('    （｡･ω･｡)つ━☆・*。');
      console.log('    ⊂　   |  　　・゜+.  🐾 LogMon Agent is Watching You!');
      console.log('    　しーＪ　　　°。+ *´`');
      console.log('===============================================');
      console.log(`  [ System Build: v${pkg.version} / Made by ksh💗 ]`);
      console.log('===============================================');
    }
  } catch (error) {
    console.error(`\n❌ 에이전트 ${isUninstall ? '제거' : '설치'} 진행 중 실패:`, error.message);
    process.exit(1);
  }
}

run();
