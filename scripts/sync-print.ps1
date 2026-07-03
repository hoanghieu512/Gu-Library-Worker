# scripts/sync-print.ps1
# Mirror the Prod _print/ queue up to a shared Google Drive folder via rclone.
# `rclone sync` is a MIRROR: files removed from _print/ (Gú ticks "Xong") are
# removed from Drive on the next run too — deletion propagation is intentional,
# so the Drive folder always equals the current print queue.
# Runs headless from a Scheduled Task; on error it logs and exits (the next
# 15-min run retries) — no in-place retry loop, no popup.
param(
    [Parameter(Mandatory = $true)][string]$KhoRoot,
    [Parameter(Mandatory = $true)][string]$RcloneRemote,   # rclone remote name, e.g. "gdrive"
    [string]$DriveDir = "GuLibrary/Di-in",
    [string]$RcloneConfig = "",                             # optional explicit --config path
    [string]$LogFile = ""
)
$ErrorActionPreference = "Stop"

$src = Join-Path $KhoRoot "_print"
if (-not $LogFile) { $LogFile = Join-Path (Split-Path -Parent $KhoRoot) "_print-sync.log" }
function Log($lvl, $msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $lvl $msg" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

try {
    if (-not (Test-Path $src)) {
        Log "INFO" "no _print/ yet, nothing to sync: $src"
        exit 0
    }
    $rcArgs = @("sync", $src, "$($RcloneRemote):$DriveDir")
    if ($RcloneConfig) { $rcArgs += @("--config", $RcloneConfig) }

    Log "INFO" "sync start: $src -> $($RcloneRemote):$DriveDir"
    $out = & rclone @rcArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw "rclone exit $LASTEXITCODE : $out" }
    Log "INFO" "sync ok"
    exit 0
} catch {
    Log "ERROR" "sync failed: $($_.Exception.Message)"
    exit 1
}
