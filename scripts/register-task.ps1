# scripts/register-task.ps1
# Registers the worker to run every few minutes on the mini PC.
param(
    [Parameter(Mandatory = $true)][string]$KhoRoot,
    [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\.."),
    [int]$IntervalMinutes = 3,
    [string]$Soffice = "C:\Program Files\LibreOffice\program\soffice.exe",
    [string]$TaskName = "GuLibraryWorker"
)

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$arguments = "-m gu_library_worker --kho `"$KhoRoot`" --soffice `"$Soffice`""

$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Gú's Library: convert + extract _inbox" -Force

Write-Host "Registered '$TaskName' every $IntervalMinutes min. Test one pass now:"
Write-Host "  $python -m gu_library_worker --kho `"$KhoRoot`" --soffice `"$Soffice`""
