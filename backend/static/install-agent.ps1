<#
.SYNOPSIS
Logmon Agent Windows 설치 스크립트
#>

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "  🚀 Logmon Agent 설치 마법사 (Windows)        " -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# 1. 관리자 권한 확인
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-Not $isAdmin) {
    Write-Host "❌ 관리자 권한이 필요합니다. PowerShell을 '관리자 권한으로 실행' 해주세요." -ForegroundColor Red
    Exit
}

# 2. 대화형 설정 입력
$backendUrl = Read-Host "백엔드 서버 주소를 입력하세요 (예: https://logmon.haroo.site)"
if ([string]::IsNullOrWhiteSpace($backendUrl)) {
    $backendUrl = "https://logmon.haroo.site"
    Write-Host "  > 입력이 없어 기본값($backendUrl)으로 설정합니다." -ForegroundColor Yellow
}

$apiKey = Read-Host "발급받은 보안 API Key를 입력하세요"
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Host "  > [경고] API Key가 비어있습니다. 서버에서 전송이 거부될 수 있습니다." -ForegroundColor Red
}

# 3. 설정 파일 생성 (~/.logmon_config.json)
$homeDir = [Environment]::GetFolderPath('UserProfile')
$configFile = Join-Path -Path $homeDir -ChildPath ".logmon_config.json"

$configData = @{
    backend_url = $backendUrl
    api_key     = $apiKey
}
$configData | ConvertTo-Json | Out-File -FilePath $configFile -Encoding utf8
Write-Host "✅ 설정 파일이 저장되었습니다: $configFile" -ForegroundColor Green

# 4. MVP용 파이썬 스크립트 매핑
# (로컬 프로젝트 최상단 기준)
$currentDir = Get-Location
$scriptPath = Join-Path -Path $currentDir -ChildPath "agent\agent_main.py"

if (-Not (Test-Path $scriptPath)) {
    Write-Host "❌ 현재 디렉터리에서 agent\agent_main.py를 찾을 수 없습니다." -ForegroundColor Red
    Write-Host "   Logmon 프로젝트 최상단 디렉터리에서 스크립트를 실행해 주세요." -ForegroundColor Yellow
    Exit
}

# 파이썬 실행 파일 경로 획득
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-Not $pythonExe) {
    $pythonExe = (Get-Command python3 -ErrorAction SilentlyContinue).Source
}

if (-Not $pythonExe) {
    Write-Host "❌ Python 설치 경로를 찾을 수 없습니다." -ForegroundColor Red
    Exit
}

Write-Host "✅ 에이전트 실행 환경 매핑 완료: $pythonExe $scriptPath" -ForegroundColor Green

# 5. 작업 스케줄러 등록
$taskName = "LogmonAgentTask"

# 멱등성: 기존 태스크 제거
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "🔄 기존 작업 스케줄러($taskName)를 제거하고 업데이트합니다..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 액션 구성 (파이썬 스크립트 실행)
$action = New-ScheduledTaskAction -Execute $pythonExe -Argument $scriptPath -WorkingDirectory $currentDir

# 트리거 구성 (시스템 시작 시 최초 1회 실행 후, 5분마다 무한 반복)
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.RepetitionInterval = (New-TimeSpan -Minutes 5)
$trigger.RepetitionDuration = [TimeSpan]::MaxValue

# 태스크 설정 (숨김 실행, 백그라운드 구동 최적화)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden

# 작업 등록
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null

Write-Host ""
Write-Host "🎉 Logmon 로컬 수집기 설치가 완료되었습니다!" -ForegroundColor Cyan
Write-Host "   Windows 작업 스케줄러를 통해 백그라운드에서 매 5분마다 로그를 전송합니다." -ForegroundColor Cyan
Write-Host "   제거를 원하시면 uninstall-agent.ps1 을 실행하세요." -ForegroundColor Cyan
