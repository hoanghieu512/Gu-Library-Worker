# scripts/register-task.ps1
# Registers the worker to run every few minutes on the mini PC.
param(
    # One or more kho roots. Pass several to watch multiple kho in one task:
    #   -KhoRoot "D:\GuLibrary\kho","D:\GuLibrary-Prod\kho"
    # They are scanned sequentially in one process (no parallel LibreOffice).
    [Parameter(Mandatory = $true)][string[]]$KhoRoot,
    [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\.."),
    [int]$IntervalMinutes = 3,
    # Optional. Leave empty to let the worker auto-detect LibreOffice
    # (GULIB_SOFFICE env var > standard install dirs > PATH). Only set this to
    # pin a non-standard soffice path.
    [string]$Soffice = "",
    [string]$TaskName = "GuLibraryWorker"
)

$ErrorActionPreference = "Stop"

# Run via pythonw.exe (no-console Python) so the task never flashes a terminal
# window each pass. Output goes nowhere, but that's fine: the worker logs to
# <kho>/_worker.log (see logsetup). Fall back to python.exe with a clear warning
# if pythonw is missing (older/partial venv) so the task still works.
$pythonw = Join-Path $RepoRoot ".venv\Scripts\pythonw.exe"
$python  = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $pythonw) {
    $exe = $pythonw
} elseif (Test-Path $python) {
    Write-Warning "pythonw.exe not found in venv; using python.exe (a console window will flash each run). Recreate the venv to get pythonw.exe."
    $exe = $python
} else {
    Write-Error "No Python found in venv: expected '$pythonw' or '$python'. Create it first: python -m venv .venv"
    exit 1
}

$arguments = "-m gu_library_worker"
foreach ($k in $KhoRoot) { $arguments += " --kho `"$k`"" }
if ($Soffice -ne "") { $arguments += " --soffice `"$Soffice`"" }

$action = New-ScheduledTaskAction -Execute $exe -Argument $arguments -WorkingDirectory $RepoRoot

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

Write-Host "Registered '$TaskName': runs every $IntervalMinutes min (indefinite), no console window."
Write-Host "Watching $($KhoRoot.Count) kho (scanned sequentially):"
foreach ($k in $KhoRoot) { Write-Host "  - $k   (log: $k\_worker.log)" }
Write-Host "Verify  : Get-ScheduledTask -TaskName $TaskName"
Write-Host "One pass (with console output): $python $arguments"
exit 0
