# scripts/notify.ps1
# Chat alerts for the Prod ops tasks (sync-print.ps1, backup.ps1). Dot-source it;
# it expects the caller to define `Log($lvl, $msg)`.
#
# Config lives OUTSIDE the repo (holds the bot token):
#   %APPDATA%\GuLibrary\notify.json  (override path with $env:GULIB_NOTIFY_CONFIG)
#   { "provider": "zalo" | "telegram", "token": "<bot token>", "chat_id": "<id>" }
#   optional "api_base" overrides the provider's base URL (used by tests).
# No config file = alerts disabled, silently. Run scripts\notify-setup.ps1 to find
# chat_id and send a test message.
#
# Alerting never breaks the task: every failure here is logged as WARN and swallowed.

$script:NotifyApiBase = @{
    zalo     = "https://bot-api.zaloplatforms.com"
    telegram = "https://api.telegram.org"
}

function Get-NotifyConfig {
    $path = $env:GULIB_NOTIFY_CONFIG
    if (-not $path) { $path = Join-Path $env:APPDATA "GuLibrary\notify.json" }
    if (-not (Test-Path $path)) { return $null }
    $cfg = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $script:NotifyApiBase.ContainsKey("$($cfg.provider)")) {
        throw "notify.json: provider must be 'zalo' or 'telegram' (got '$($cfg.provider)')"
    }
    if (-not $cfg.token) { throw "notify.json: token is empty" }
    $base = if ($cfg.api_base) { $cfg.api_base } else { $script:NotifyApiBase["$($cfg.provider)"] }
    return [pscustomobject]@{
        Provider = "$($cfg.provider)"; Token = "$($cfg.token)"
        ChatId   = "$($cfg.chat_id)";  Base  = $base.TrimEnd("/")
    }
}

# Zalo and Telegram share the same bot API shape: POST <base>/bot<token>/<method>.
function Invoke-BotApi($cfg, $method, $body, [int]$TimeoutSec = 30) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor
        [Net.SecurityProtocolType]::Tls12
    # PS 5.1 encodes a string body as ISO-8859-1; send UTF-8 bytes explicitly.
    $bytes = [Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Compress))
    return Invoke-RestMethod -Method Post -Uri "$($cfg.Base)/bot$($cfg.Token)/$method" `
        -ContentType "application/json; charset=utf-8" -Body $bytes -TimeoutSec $TimeoutSec
}

function Send-Notify([string]$text) {
    try {
        $cfg = Get-NotifyConfig
        if (-not $cfg) { return $false }
        if (-not $cfg.ChatId) { throw "notify.json: chat_id is empty (run notify-setup.ps1)" }
        if ($text.Length -gt 1900) { $text = $text.Substring(0, 1900) + " ..." }  # Zalo max 2000
        $resp = Invoke-BotApi $cfg "sendMessage" @{ chat_id = $cfg.ChatId; text = $text }
        if (-not $resp.ok) { throw "sendMessage returned ok=false: $($resp | ConvertTo-Json -Compress)" }
        Log "INFO" "notify sent ($($cfg.Provider))"
        return $true
    } catch {
        Log "WARN" "notify failed: $($_.Exception.Message)"
        return $false
    }
}

# Track task health in a small state file next to the task log and alert on edges:
#   - failing continuously for >= $AlertAfterMinutes -> ALERT (repeat every
#     $RepeatAfterHours while still failing)
#   - first success after an ALERT                   -> RECOVERED
#   - $NotifyOk                                     -> OK message on every success
#     (weekly backup: doubles as a heartbeat — no Sunday message = look at the box)
function Update-TaskHealth {
    param(
        [Parameter(Mandatory = $true)][string]$StateFile,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][bool]$Ok,
        [string]$Detail = "",
        [string]$LogPath = "",
        [int]$AlertAfterMinutes = 120,
        [int]$RepeatAfterHours = 24,
        [switch]$NotifyOk
    )
    try {
        $now = Get-Date
        $st = @{ firstFail = $null; lastAlert = $null; lastOk = $null }
        if (Test-Path $StateFile) {
            $raw = Get-Content $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($k in @("firstFail", "lastAlert", "lastOk")) { if ($raw.$k) { $st[$k] = [datetime]$raw.$k } }
        }
        $fmt = "yyyy-MM-dd HH:mm"
        if ($Ok) {
            if ($st.lastAlert) {
                Send-Notify "[$Label] RECOVERED - ok again at $($now.ToString($fmt)) (failing since $($st.firstFail.ToString($fmt)))." | Out-Null
            } elseif ($NotifyOk) {
                Send-Notify "[$Label] OK - $($now.ToString($fmt)). $Detail".TrimEnd() | Out-Null
            }
            $st = @{ firstFail = $null; lastAlert = $null; lastOk = $now }
        } else {
            if (-not $st.firstFail) { $st.firstFail = $now }
            $failingMin = ($now - $st.firstFail).TotalMinutes
            $due = if ($st.lastAlert) { ($now - $st.lastAlert).TotalHours -ge $RepeatAfterHours }
                   else { $failingMin -ge $AlertAfterMinutes }
            if ($due) {
                $last = if ($st.lastOk) { $st.lastOk.ToString($fmt) } else { "unknown" }
                $sent = Send-Notify ("[$Label] FAILING since $($st.firstFail.ToString($fmt)) " +
                    "(last ok: $last). Error: $Detail. Log: $LogPath")
                if ($sent) { $st.lastAlert = $now }
            }
        }
        $out = @{}
        foreach ($k in $st.Keys) { $out[$k] = if ($st[$k]) { $st[$k].ToString("o") } else { $null } }
        $out | ConvertTo-Json | Out-File -FilePath $StateFile -Encoding utf8
    } catch {
        Log "WARN" "health state update failed: $($_.Exception.Message)"
    }
}
