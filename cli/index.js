#!/usr/bin/env node

const { execSync } = require('child_process');
const pkg = require('./package.json');

// 전체 인자 중 'uninstall'이 포함되어 있는지 견고하게 확인
const isUninstall = process.argv.includes('uninstall');

let apiKey = "default_dev_key";
let backendUrl = "http://localhost:3008/api/logmon";

// HTTP/HTTPS 프로토콜로 시작하는 인자 검색 (방어적 파싱)
const foundUrl = process.argv.find(arg => arg.startsWith('http://') || arg.startsWith('https://'));

if (isUninstall) {
  backendUrl = foundUrl || process.env.BACKEND_URL || "http://localhost:3008/api/logmon";
} else {
  // uninstall이 아닌 설치 시 첫 번째 인자는 API Key로 처리하되, 그 값이 URL이 아닐 때만 API Key로 사용
  const firstArg = process.argv[2];
  if (firstArg && !firstArg.startsWith('http://') && !firstArg.startsWith('https://')) {
    apiKey = firstArg;
  } else {
    apiKey = process.env.API_KEY || "default_dev_key";
  }
  backendUrl = foundUrl || process.env.BACKEND_URL || "http://localhost:3008/api/logmon";
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
      // 쉘스크립트 출력 형식을 완벽하게 시뮬레이션하여 검증력 극대화
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
    
    // 설치 성공 시 이스터에그 및 원 기획 내용 완벽 출력
    console.log('\n🎉 Logmon 로컬 수집기 설치가 완료되었습니다!');
    console.log(`   제거 명령어: npx @thiagomiki/logmon-cli@latest uninstall ${backendUrl}\n`);
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
