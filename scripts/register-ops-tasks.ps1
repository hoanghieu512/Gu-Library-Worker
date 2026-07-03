# scripts/register-ops-tasks.ps1
# Register the two Prod-only ops Scheduled Tasks (independent of GuLibraryWorker):
#   GuLibraryPrintSync - every N minutes, mirror _print/ -> Drive GuLibrary/Di-in
#   GuLibraryBackup    - weekly, dated snapshot + mirror to Drive GuLibrary/Backup
# Run in an ADMINISTRATOR PowerShell. Tasks run whether logged on or not (S4U) so
# they survive reboot with no logon, and headless (session 0, no window).
param(
    [Parameter(Mandatory = $true)][string]$KhoRoot,
    [Parameter(Mandatory = $true)][string]$RcloneRemote,   # rclone remote name, e.g. "gdrive"
    [string]$RepoRoot = "",
    [string]$RcloneConfig = "",                             # optional explicit --config path
    [int]$PrintIntervalMinutes = 15,
    [string]$BackupDayOfWeek = "Sunday",
    [string]$BackupAt = "03:00"
)
$ErrorActionPreference = "Stop"

# Resolve repo root from THIS script's path ($PSScriptRoot is unreliable in a
# param default under -File; see register-task.ps1 v0.8.3).
if (-not $RepoRoot) {
    $scriptPath = if ($PSCommandPath) { $PSCommandPath } else { $MyInvocation.MyCommand.Path }
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $scriptPath)
}
$RepoRoot = (Resolve-Path $RepoRoot).Path

$syncScript   = Join-Path $RepoRoot "scripts\sync-print.ps1"
$backupScript = Join-Path $RepoRoot "scripts\backup.ps1"
foreach ($s in @($syncScript, $backupScript)) {
    if (-not (Test-Path $s)) { Write-Error "missing script: $s"; exit 1 }
}

# S4U = run whether the user is logged on or not, no stored password. Runs headless
# (session 0) so no console window, and uses the user's rclone config in %APPDATA%.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

function Register-Verified($name, $action, $trigger) {
    try {
        Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
    } catch {
        Write-Error "Failed to register '$name' (run PowerShell as Administrator?): $($_.Exception.Message)"
        exit 1
    }
    if (-not (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue)) {
        Write-Error "Registration reported no error but '$name' was not created."
        exit 1
    }
    Write-Host "Registered '$name'."
}

function New-PsArg($script, $extra) {
    $a = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" " +
         "-KhoRoot `"$KhoRoot`" -RcloneRemote `"$RcloneRemote`""
    if ($RcloneConfig) { $a += " -RcloneConfig `"$RcloneConfig`"" }
    return $a + $extra
}

# --- GuLibraryPrintSync: every N minutes, indefinitely ---
$printAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (New-PsArg $syncScript "")
# Indefinite repetition without an out-of-range duration (register-task.ps1 v0.7.9).
$printTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date)
$printTrigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $PrintIntervalMinutes)).Repetition
Register-Verified "GuLibraryPrintSync" $printAction $printTrigger

# --- GuLibraryBackup: weekly ---
$backupAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (New-PsArg $backupScript "")
$backupTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $BackupDayOfWeek -At $BackupAt
Register-Verified "GuLibraryBackup" $backupAction $backupTrigger

$logDir = Split-Path -Parent $KhoRoot
Write-Host ""
Write-Host "Both ops tasks registered (Prod)."
Write-Host "  GuLibraryPrintSync : every $PrintIntervalMinutes min -> $($RcloneRemote):GuLibrary/Di-in"
Write-Host "  GuLibraryBackup    : $BackupDayOfWeek $BackupAt -> snapshot + $($RcloneRemote):GuLibrary/Backup"
Write-Host "Verify: Get-ScheduledTask GuLibraryPrintSync,GuLibraryBackup | Format-Table TaskName,State"
Write-Host "Logs  : $logDir\_print-sync.log , $logDir\_backup.log"
exit 0
