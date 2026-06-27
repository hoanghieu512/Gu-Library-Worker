# scripts/register-task.ps1
# Registers the worker to run every few minutes on the mini PC.
param(
    [Parameter(Mandatory = $true)][string]$KhoRoot,
    [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\.."),
    [int]$IntervalMinutes = 3,
    # Optional. Leave empty to let the worker auto-detect LibreOffice
    # (GULIB_SOFFICE env var > standard install dirs > PATH). Only set this to
    # pin a non-standard soffice path.
    [string]$Soffice = "",
    [string]$TaskName = "GuLibraryWorker"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$arguments = "-m gu_library_worker --kho `"$KhoRoot`""
if ($Soffice -ne "") { $arguments += " --soffice `"$Soffice`"" }

$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $RepoRoot

# Repeat every N minutes, indefinitely. Do NOT set -RepetitionDuration to a huge
# value: [TimeSpan]::MaxValue serializes to P99999999DT23H59M59S, which Task
# Scheduler rejects as out of range (0x80041318). Copying the Repetition object
# from a freshly built repeating trigger leaves Duration empty = run forever,
# which is the supported way to get indefinite repetition.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date)
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)).Repetition

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# Register, then VERIFY — never claim success on a silent/failed registration.
try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Description "Gu's Library: convert + extract _inbox" -Force | Out-Null
} catch {
    Write-Error "Failed to register '$TaskName': $($_.Exception.Message)"
    exit 1
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Error "Registration reported no error but '$TaskName' was not created."
    exit 1
}

Write-Host "Registered '$TaskName': runs every $IntervalMinutes min (indefinite)."
Write-Host "Verify : Get-ScheduledTask -TaskName $TaskName"
Write-Host "One pass: $python $arguments"
exit 0
