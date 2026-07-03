# scripts/backup.ps1
# Weekly Prod backup chain: dated local snapshot of the kho, keep the newest N,
# then mirror the snapshot folder to Google Drive via rclone.
#   <kho-parent>\backup\YYYY-MM-DD\   (sibling of kho -> OUTSIDE the Syncthing tree)
# Depth of time beyond .stversions + a real offsite copy.
# Runs headless from a Scheduled Task; on error it logs and exits (next week's run
# retries) — no in-place retry loop, no popup. `-SkipDrive` = local snapshot only.
param(
    [Parameter(Mandatory = $true)][string]$KhoRoot,
    [string]$RcloneRemote = "",                            # empty or -SkipDrive => local only
    [string]$DriveDir = "GuLibrary/Backup",
    [string]$RcloneConfig = "",
    [int]$Keep = 4,
    [switch]$SkipDrive,
    [string]$LogFile = ""
)
$ErrorActionPreference = "Stop"

$parent = Split-Path -Parent $KhoRoot
$backupDir = Join-Path $parent "backup"
if (-not $LogFile) { $LogFile = Join-Path $parent "_backup.log" }
function Log($lvl, $msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $lvl $msg" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

try {
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $dest = Join-Path $backupDir (Get-Date -Format 'yyyy-MM-dd')

    Log "INFO" "snapshot start: $KhoRoot -> $dest"
    # Mirror the kho into today's dated folder, excluding Syncthing's own version
    # history (.stversions) so the snapshot stays lean. robocopy exit < 8 = success.
    robocopy $KhoRoot $dest /MIR /XD (Join-Path $KhoRoot ".stversions") /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }
    Log "INFO" "snapshot done: $dest"

    # Retention: keep the newest $Keep dated snapshots (YYYY-MM-DD sorts chronologically).
    $stale = Get-ChildItem $backupDir -Directory |
        Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' } |
        Sort-Object Name -Descending | Select-Object -Skip $Keep
    foreach ($d in $stale) {
        Remove-Item $d.FullName -Recurse -Force
        Log "INFO" "pruned old snapshot: $($d.Name)"
    }

    if ($SkipDrive -or -not $RcloneRemote) {
        Log "INFO" "Drive sync skipped (local snapshot only)"
        exit 0
    }
    $rcArgs = @("sync", $backupDir, "$($RcloneRemote):$DriveDir")
    if ($RcloneConfig) { $rcArgs += @("--config", $RcloneConfig) }
    Log "INFO" "drive sync start: $backupDir -> $($RcloneRemote):$DriveDir"
    $out = & rclone @rcArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw "rclone exit $LASTEXITCODE : $out" }
    Log "INFO" "drive sync ok"
    exit 0
} catch {
    Log "ERROR" "backup failed: $($_.Exception.Message)"
    exit 1
}
