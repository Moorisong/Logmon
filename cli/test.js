const test = require('node:test');
const assert = require('node:assert');
const { execSync } = require('child_process');
const path = require('path');

const cliPath = path.join(__dirname, 'index.js');

test('CLI 에이전트 설치 출력 포맷 검증', (t) => {
  // LOGMON_TEST_MODE=true 주입하여 실행
  const output = execSync(`node "${cliPath}" my_api_key http://localhost:8000/api/logmon`, {
    env: { ...process.env, LOGMON_TEST_MODE: 'true' },
    encoding: 'utf8'
  });

  // 1. 설치기 상단 타이틀 검증
  assert.ok(output.includes('👾 LogMon CLI 에이전트 무중단 설치기'), '설치기 타이틀이 출력되어야 합니다.');
  
  // 2. 쉘 가상 출력 검증
  assert.ok(output.includes('서버 주소: http://localhost:8000/api/logmon'), '입력된 백엔드 URL이 출력되어야 합니다.');
  assert.ok(output.includes('보안 인증: 매핑 완료!'), '보안 인증 매핑 완료 메시지가 있어야 합니다.');
  
  // 3. 고양이 이스터에그 검증
  assert.ok(output.includes('🐾 LogMon Agent is Watching You!'), '고양이 이스터에그가 정확히 렌더링되어야 합니다.');
  assert.ok(output.includes('（｡･ω･｡)つ━☆・*。'), '고양이 아스키 아동작이 포함되어야 합니다.');
  
  // 4. 시스템 빌드 및 정보 푸터 검증
  assert.ok(output.includes('System Build: v'), '시스템 빌드 정보가 출력되어야 합니다.');
  assert.ok(output.includes('Made by ksh💗'), '제작자 표기가 있어야 합니다.');
  
  // 5. 중복 타이틀 불포함 검증 (제거 마법사가 섞여 나오지 않는지)
  assert.ok(!output.includes('🧹 Logmon Agent 제거 마법사'), '설치 모드에서 제거 마법사 타이틀이 노출되면 안 됩니다.');
});

test('CLI 에이전트 제거 출력 포맷 검증', (t) => {
  const output = execSync(`node "${cliPath}" uninstall http://localhost:8000/api/logmon`, {
    env: { ...process.env, LOGMON_TEST_MODE: 'true' },
    encoding: 'utf8'
  });

  // 1. 제거기 전용 타이틀 검증
  assert.ok(output.includes('🧹 Logmon Agent 제거 마법사 (macOS/Linux)'), '제거 마법사 타이틀이 출력되어야 합니다.');
  
  // 2. 제거 로그 메시지 검증
  assert.ok(output.includes('macOS LaunchAgent(com.logmon.agent) 데몬을 중지합니다...'), '데몬 중지 메시지가 있어야 합니다.');
  assert.ok(output.includes('PLIST 파일이 제거되었습니다.'), 'PLIST 제거 메시지가 있어야 합니다.');
  assert.ok(output.includes('Logmon 에이전트가 시스템에서 완전히 제거되었습니다!'), '완료 안내 문구가 포함되어야 합니다.');
  
  // 3. 설치기 잔재 배제 검증 (매우 중요)
  assert.ok(!output.includes('👾 LogMon CLI 에이전트 무중단 설치기'), '제거 모드에서 설치기 타이틀이 노출되면 안 됩니다.');
  assert.ok(!output.includes('🐾 LogMon Agent is Watching You!'), '제거 모드에서 고양이 이스터에그가 노출되면 안 됩니다.');
  assert.ok(!output.includes('Made by ksh💗'), '제작자 정보 푸터가 제거 모드에서 노출되면 안 됩니다.');
});
