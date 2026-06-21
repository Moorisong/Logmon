#!/usr/bin/env node

const { execSync } = require('child_process');
const pkg = require('./package.json');

// 전체 인자 중 'uninstall'이 포함되어 있는지 확인
const isUninstall = process.argv.some(arg => arg.toLowerCase().includes('uninstall'));

async function run() {
  // 버전 확인 파라미터 체크 (-v, --version)
  const isVersion = process.argv.includes('--version') || process.argv.includes('-v') || process.argv.includes('version');
  if (isVersion) {
    console.log(`logmon v${pkg.version}`);
    process.exit(0);
  }

  // [인프라 일원화] 우리 서버의 안전한 공식 SSL 도메인 관문 고정
  const BASE_URL = "https://logmon.haroo.site";

  // 터미널 화면 깔끔하게 청소
  process.stdout.write('\x1Bc');

  if (!isUninstall) {
    console.log('===============================================');
    console.log('  👾 LogMon CLI 에이전트 자동 설치기 (No-Input)');
    console.log('===============================================');
    console.log('🔄 서버로부터 개인화된 보안 설정을 동기화하는 중...');
  } else {
    console.log('===============================================');
    console.log('  Clean Cap 🧹 Logmon Agent 제거 마법사');
    console.log('===============================================');
  }

  try {
    if (isUninstall) {
      // [★ 영구 패치 완료] 정적 파일 간섭을 완전히 배제하기 위해 백엔드 스트리밍 전용 API 주소로 전격 전환!
      const uninstallCmd = `curl -sL ${BASE_URL}/api/logmon/agent-uninstall-script | bash`;
      execSync(uninstallCmd, { stdio: 'inherit' });
    } else {
      // [핵심] 정적 파일이 아닌, 백엔드가 키를 동적으로 구워내는 '라우터 API'를 직접 파이프로 실행!
      const installCmd = `curl -sL ${BASE_URL}/api/logmon/agent-setup-script | bash`;
      execSync(installCmd, { stdio: 'inherit' });
      
      console.log('\n🎉 Logmon 로컬 수집기 동기화가 완전히 끝났습니다!');
      console.log(`   제거를 원하시면: npx logmon-cli uninstall\n`);
      console.log('      /\\_/\\   ');
      console.log('    （｡･ω･｡)つ━☆・*。');
      console.log('    ⊂    |    ・゜+.  🐾 LogMon Agent is Watching You!');
      console.log('     しーＪ   °。+ *´`');
      console.log('===============================================');
      console.log(`  [ System Build: v${pkg.version} / Powered by SSL ]`);
      console.log('===============================================');
    }
  } catch (error) {
    console.error(`\n❌ 에이전트 ${isUninstall ? '제거' : '설치'} 진행 중 실패:`, error.message);
    process.exit(1);
  }
}

run();