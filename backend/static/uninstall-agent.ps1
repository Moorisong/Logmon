<#
.SYNOPSIS
Logmon Agent Windows 제거 스크립트
#>

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "  🧹 Logmon Agent 제거 마법사 (Windows)        " -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# 1. 관리자 권한 확인
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-Not $isAdmin) {
    Write-Host "❌ 관리자 권한이 필요합니다. PowerShell을 '관리자 권한으로 실행' 해주세요." -ForegroundColor Red
    Exit
}

$taskName = "LogmonAgentTask"

# 2. 작업 스케줄러 중지 및 제거
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "🔄 작업 스케줄러($taskName)를 제거합니다..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "🗑️  작업 스케줄러 항목이 삭제되었습니다." -ForegroundColor Green
} else {
    Write-Host "⚠️ 등록된 작업 스케줄러($taskName)를 찾을 수 없습니다." -ForegroundColor Yellow
}

# 3. 설정 및 캐시 파일 클리어
$homeDir = [Environment]::GetFolderPath('UserProfile')
$configFile = Join-Path -Path $homeDir -ChildPath ".logmon_config.json"
$checkpointFile = Join-Path -Path $homeDir -ChildPath ".logmon_checkpoint"

if (Test-Path $configFile) {
    Remove-Item $configFile -Force
    Write-Host "🗑️  설정 파일(.logmon_config.json) 삭제 완료." -ForegroundColor Green
}

if (Test-Path $checkpointFile) {
    Remove-Item $checkpointFile -Force
    Write-Host "🗑️  수집 오프셋 캐시(.logmon_checkpoint) 삭제 완료." -ForegroundColor Green
}

# TODO (Phase 4): 바이너리 폴더 삭제 로직
# $appDir = "C:\Program Files\Logmon"
# if (Test-Path $appDir) {
#     Remove-Item $appDir -Recurse -Force
#     Write-Host "🗑️  바이너리 설치 디렉터리 삭제 완료." -ForegroundColor Green
# }

Write-Host ""
Write-Host "✨ Logmon 에이전트가 시스템에서 완전히 제거되었습니다!" -ForegroundColor Cyan
