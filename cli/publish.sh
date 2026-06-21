#!/usr/bin/env bash
set -e

# CLI 디렉터리로 이동 (스크립트 위치 기준)
cd "$(dirname "$0")"

echo "==============================================="
echo "  📦 LogMon CLI 배포 스크립트"
echo "==============================================="

# 1. 버전업 타입 결정 (기본값: patch)
VERSION_TYPE=${1:-patch}
if [[ "$VERSION_TYPE" != "patch" && "$VERSION_TYPE" != "minor" && "$VERSION_TYPE" != "major" ]]; then
    echo "❌ 올바르지 않은 버전업 타입입니다. (patch, minor, major 중 입력)"
    exit 1
fi

echo "🔄 npm version $VERSION_TYPE 진행 중..."
NEW_VERSION=$(npm version "$VERSION_TYPE" --no-git-tag-version)
echo "✅ package.json 버전 갱신 완료: $NEW_VERSION"

# 2. npm 로그인 상태 확인
echo "🔍 npm 로그인 상태 확인 중..."
if ! npm whoami > /dev/null 2>&1; then
    echo "❌ npm에 로그인되어 있지 않습니다. 'npm login'을 먼저 수행해 주세요."
    exit 1
fi

# 3. 배포 진행
echo "🚀 npm publish 진행 중..."
npm publish --access public

echo "==============================================="
echo "  🎉 CLI 배포 완료! ($NEW_VERSION)"
echo "==============================================="
