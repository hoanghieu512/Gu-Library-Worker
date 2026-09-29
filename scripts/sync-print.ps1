# scripts/sync-print.ps1
# Mirror the Prod _print/ queue up to a shared Google Drive folder via rclone.
# `rclone sync` is a MIRROR: files removed from _print/ (Gú ticks "Xong") are
# removed from Drive on the next run too — deletion propagation is intentional,
# so the Drive folder always equals the current print queue.
# Runs headless from a Scheduled Task; on error it logs and exits (the next
# 15-min run retries) — no in-place retry loop, no popup. If it keeps failing for
# -AlertAfterMinutes, a chat alert goes out (scripts\notify.ps1), then RECOVERED.
# A gap of -GapAlertMinutes since the previous run (power cut, hang) is reported
# when it runs again - nothing on this box can alert while it is down.
param(
    [Parameter(Mandatory = $true)][string]$KhoRoot,
    [Parameter(Mandatory = $true)][string]$RcloneRemote,   # rclone remote name, e.g. "gdrive"
    [string]$DriveDir = "GuLibrary/Di-in",
    [string]$RcloneConfig = "",                             # optional explicit --config path
    [string]$LogFile = "",
    [int]$AlertAfterMinutes = 120,
    [int]$GapAlertMinutes = 60     # runs every 15 min; a longer gap = the box was down
)
$ErrorActionPreference = "Stop"

$src = Join-Path $KhoRoot "_print"
if (-not $LogFile) { $LogFile = Join-Path (Split-Path -Parent $KhoRoot) "_print-sync.log" }
function Log($lvl, $msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $lvl $msg" | Out-File -FilePath $LogFile -Append -Encoding utf8
}
. (Join-Path $PSScriptRoot "notify.ps1")
$health = @{
    StateFile = [IO.Path]::ChangeExtension($LogFile, ".state.json")
    EnvName   = Split-Path -Leaf (Split-Path -Parent $KhoRoot)
    Task      = "print-sync"
    LogPath   = $LogFile
    AlertAfterMinutes = $AlertAfterMinutes
    GapAlertMinutes   = $GapAlertMinutes
}

try {
    if (-not (Test-Path $src)) {
        Log "INFO" "no _print/ yet, nothing to sync: $src"
        Update-TaskHealth @health -Ok $true
        exit 0
    }
    $rcArgs = @("sync", $src, "$($RcloneRemote):$DriveDir")
    if ($RcloneConfig) { $rcArgs += @("--config", $RcloneConfig) }

    Log "INFO" "sync start: $src -> $($RcloneRemote):$DriveDir"
    # rclone writes NOTICE lines to stderr even on success (e.g. clock skew). Under
    # Windows PowerShell 5.1 with ErrorActionPreference=Stop, a redirected stderr line
    # becomes a terminating error that aborts the run before rclone finishes — so relax
    # it for this call and judge success by the exit code alone.
    $ErrorActionPreference = "Continue"
    $out = @(& rclone @rcArgs 2>&1 | ForEach-Object { "$_" })
    $code = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($code -ne 0) { throw "rclone exit $code : $($out -join ' | ')" }
    if ($out) { Log "WARN" "rclone: $($out -join ' | ')" }
    Log "INFO" "sync ok"
    Update-TaskHealth @health -Ok $true
    exit 0
} catch {
    $err = $_.Exception.Message
    Log "ERROR" "sync failed: $err"
    Update-TaskHealth @health -Ok $false -Detail $err
    exit 1
}
