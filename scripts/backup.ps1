# scripts/backup.ps1
# Weekly Prod backup chain: dated local snapshot of the kho, keep the newest N,
# then mirror the snapshot folder to Google Drive via rclone.
#   <kho-parent>\backup\YYYY-MM-DD\   (sibling of kho -> OUTSIDE the Syncthing tree)
# Depth of time beyond .stversions + a real offsite copy.
# Runs headless from a Scheduled Task; on error it logs and exits (next week's run
# retries) — no in-place retry loop, no popup. `-SkipDrive` = local snapshot only.
# Every run sends a chat message (scripts\notify.ps1): OK on success — a weekly
# heartbeat, so a missing Sunday message means "look at the box" — or FAILING.
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
. (Join-Path $PSScriptRoot "notify.ps1")
# Weekly task: alert on the first failure (the next retry is a week away).
$health = @{
    StateFile = [IO.Path]::ChangeExtension($LogFile, ".state.json")
    EnvName   = Split-Path -Leaf $parent
    Task      = "backup"
    LogPath   = $LogFile
    AlertAfterMinutes = 0
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
        Update-TaskHealth @health -Ok $true -OkMessage "backup_ok_local" -Vars @{ snapshot = Split-Path -Leaf $dest }
        exit 0
    }
    $rcArgs = @("sync", $backupDir, "$($RcloneRemote):$DriveDir")
    if ($RcloneConfig) { $rcArgs += @("--config", $RcloneConfig) }
    Log "INFO" "drive sync start: $backupDir -> $($RcloneRemote):$DriveDir"
    # Same PowerShell 5.1 stderr trap as sync-print.ps1: a harmless rclone NOTICE must
    # not abort the run — judge success by the exit code alone.
    $ErrorActionPreference = "Continue"
    $out = @(& rclone @rcArgs 2>&1 | ForEach-Object { "$_" })
    $code = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($code -ne 0) { throw "rclone exit $code : $($out -join ' | ')" }
    if ($out) { Log "WARN" "rclone: $($out -join ' | ')" }
    Log "INFO" "drive sync ok"
    Update-TaskHealth @health -Ok $true -OkMessage "backup_ok" -Vars @{ snapshot = Split-Path -Leaf $dest }
    exit 0
} catch {
    $err = $_.Exception.Message
    Log "ERROR" "backup failed: $err"
    Update-TaskHealth @health -Ok $false -Detail $err
    exit 1
}
