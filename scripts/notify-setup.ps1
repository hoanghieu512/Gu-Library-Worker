# scripts/notify-setup.ps1
# One-time setup for ops chat alerts (see scripts\notify.ps1). Run as the SAME
# Windows user the Scheduled Tasks run as (the config lives in that user's %APPDATA%).
#   1st run : creates %APPDATA%\GuLibrary\notify.json -> fill in provider + token.
#   then    : message your bot once from the phone, run again -> finds chat_id,
#             saves it, sends a test message.
# Never prints the token.
param(
    [switch]$Test   # only send a test message with the saved config
)
$ErrorActionPreference = "Stop"
function Log($lvl, $msg) { Write-Host "$lvl $msg" }
. (Join-Path $PSScriptRoot "notify.ps1")

$path = $env:GULIB_NOTIFY_CONFIG
if (-not $path) { $path = Join-Path $env:APPDATA "GuLibrary\notify.json" }

if (-not (Test-Path $path)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    [ordered]@{ provider = "zalo"; token = ""; chat_id = "" } | ConvertTo-Json |
        Out-File -FilePath $path -Encoding utf8
    Write-Host "Created $path"
    Write-Host "Next: put your bot token in it (provider 'zalo' or 'telegram'),"
    Write-Host "send any message to the bot from your phone, then run this script again."
    exit 0
}

$cfg = Get-NotifyConfig
if (-not $Test -and -not $cfg.ChatId) {
    # Zalo returns one update object, Telegram an array; normalise both.
    $resp = Invoke-BotApi $cfg "getUpdates" @{ timeout = "10" }
    $chats = @(@($resp.result) | Where-Object { $_.message.chat.id } | ForEach-Object {
        $from = $_.message.from
        $name = if ($from.display_name) { $from.display_name } else { "$($from.first_name) $($from.last_name)".Trim() }
        [pscustomobject]@{ ChatId = "$($_.message.chat.id)"; From = $name; Text = $_.message.text }
    } | Sort-Object ChatId -Unique)
    if ($chats.Count -eq 0) {
        Write-Host "No messages found. Send any message to the bot from your phone, then run again."
        exit 1
    }
    if ($chats.Count -gt 1) {
        $chats | Format-Table -AutoSize | Out-String | Write-Host
        Write-Host "Several chats found - put the right chat_id into $path by hand, then run with -Test."
        exit 1
    }
    $raw = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $raw.chat_id = $chats[0].ChatId
    $raw | ConvertTo-Json | Out-File -FilePath $path -Encoding utf8
    Write-Host "Saved chat_id $($chats[0].ChatId) (from '$($chats[0].From)')."
}

if (Send-Notify "[GuLibrary] Test alert from $env:COMPUTERNAME - notifications are working.") {
    Write-Host "Test message sent. Check your phone."
    exit 0
}
Write-Host "Test message FAILED - see the WARN line above."
exit 1
