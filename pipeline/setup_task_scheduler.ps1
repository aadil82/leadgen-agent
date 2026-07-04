# ═══════════════════════════════════════════════════════════════
#  LinkedIn SDR Agent — Windows Task Scheduler Setup
#  Run this script ONCE as Administrator to register the daily task.
#
#  Usage (in PowerShell as Admin):
#    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#    .\pipeline\setup_task_scheduler.ps1
#
#  To remove the task:
#    Unregister-ScheduledTask -TaskName "LeadGenAgent_DailyPipeline" -Confirm:$false
# ═══════════════════════════════════════════════════════════════

param(
    [string]$TaskName = "LeadGenAgent_DailyPipeline",
    [string]$RunTime = "08:00",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

# ── Remove existing task if requested ──────────────────────────
if ($Remove) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "✅ Task '$TaskName' removed." -ForegroundColor Green
    } catch {
        Write-Host "ℹ️  Task '$TaskName' not found." -ForegroundColor Yellow
    }
    exit 0
}

# ── Check for admin privileges ─────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "⚠️  This script must be run as Administrator." -ForegroundColor Red
    Write-Host "   Right-click PowerShell → Run as Administrator" -ForegroundColor Yellow
    exit 1
}

# ── Paths ──────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$BatchScript = Join-Path $ScriptDir "run_daily.bat"
$LogDir = Join-Path $ProjectDir "data\logs"

# Create logs directory
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# ── Remove old task if exists ─────────────────────────────────
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

# ── Create the scheduled task ─────────────────────────────────
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatchScript`"" `
    -WorkingDirectory $ProjectDir

# Daily trigger at the specified time
$Trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At $RunTime

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

# Register the task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "LinkedIn SDR Agent — Automated daily lead generation pipeline" `
    -RunLevel Highest `
    -Force

Write-Host ""
Write-Host "✅ Task '$TaskName' registered successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "  Schedule:  Daily at $RunTime" -ForegroundColor Cyan
Write-Host "  Script:    $BatchScript" -ForegroundColor Cyan
Write-Host "  Logs:      $LogDir\pipeline_*.log" -ForegroundColor Cyan
Write-Host "  Project:   $ProjectDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "To run manually:" -ForegroundColor Yellow
Write-Host "  schtasks /Run /TN `"$TaskName`"" -ForegroundColor White
Write-Host ""
Write-Host "To remove:" -ForegroundColor Yellow
Write-Host "  .\pipeline\setup_task_scheduler.ps1 -Remove" -ForegroundColor White
Write-Host "  # OR" -ForegroundColor Gray
Write-Host "  Unregister-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor White
Write-Host ""
Write-Host "To change the run time:" -ForegroundColor Yellow
Write-Host "  .\pipeline\setup_task_scheduler.ps1 -RunTime `"09:30`"" -ForegroundColor White
Write-Host ""
