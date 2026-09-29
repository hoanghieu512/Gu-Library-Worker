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

# User-facing wording (Vietnamese) lives in notify-messages.json next to this file,
# so it can be edited without touching code. Placeholders: {name}.
$script:NotifyMessagesPath = Join-Path $PSScriptRoot "notify-messages.json"

function Get-NotifyMessages {
    Get-Content $script:NotifyMessagesPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Format-NotifyText([string]$template, [hashtable]$vars) {
    foreach ($k in $vars.Keys) { $template = $template.Replace("{$k}", "$($vars[$k])") }
    return $template
}

# Render message $key; if the messages file is missing/broken, fall back to a plain
# dump so an alert still goes out.
function Get-NotifyText([string]$key, [hashtable]$vars) {
    try {
        $m = Get-NotifyMessages
        if (-not $m.$key) { throw "no message '$key'" }
        return Format-NotifyText $m.$key $vars
    } catch {
        Log "WARN" "notify messages: $($_.Exception.Message)"
        return "[$key] " + (($vars.Keys | Sort-Object | ForEach-Object { "${_}: $($vars[$_])" }) -join " | ")
    }
}

# Map a raw error to a plain-language reason + fix via the ordered "errors" list
# (first regex match wins).
function Get-ErrorExplanation([string]$raw) {
    try {
        $m = Get-NotifyMessages
        foreach ($e in $m.errors) { if ($raw -match $e.match) { return $e } }
        return $m.error_unknown
    } catch {
        return [pscustomobject]@{ reason = "?"; fix = "?" }
    }
}

# "2 giờ 5 phút" etc., unit words from the messages file.
function Format-NotifyDuration([TimeSpan]$span) {
    try { $m = Get-NotifyMessages } catch { return "$([int]$span.TotalMinutes) min" }
    $vars = @{ d = $span.Days; h = $span.Hours; m = $span.Minutes }
    $key = if ($span.TotalDays -ge 1) { "duration_d" } elseif ($span.TotalHours -ge 1) { "duration_h" } else { "duration_m" }
    return Format-NotifyText $m.$key $vars
}

function Get-LastBootTime {
    try { return (Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).LastBootUpTime } catch { return $null }
}

# Track task health in a small state file next to the task log and alert on edges:
#   - failing continuously for >= $AlertAfterMinutes -> "failing" (repeat every
#     $RepeatAfterHours while still failing), with reason + fix + raw error
#   - first success after an alert                   -> "recovered"
#   - first success after a failure long enough to alert, but the alert never got
#     out (e.g. the box itself was offline)          -> "recovered_unreported"
#   - $GapAlertMinutes > 0 and the previous run is older than that (power cut, hang,
#     sleep: nothing ran, so nothing could alert)   -> "downtime" when it runs again
#   - $OkMessage set                                 -> that message on every success
#     (weekly backup: doubles as a heartbeat - no Sunday message = look at the box)
function Update-TaskHealth {
    param(
        [Parameter(Mandatory = $true)][string]$StateFile,
        [Parameter(Mandatory = $true)][string]$EnvName,   # e.g. "GuLibrary-Prod"
        [Parameter(Mandatory = $true)][string]$Task,      # key under "tasks" in the messages file
        [Parameter(Mandatory = $true)][bool]$Ok,
        [string]$Detail = "",                             # raw error when -Ok $false
        [string]$LogPath = "",
        [int]$AlertAfterMinutes = 120,
        [int]$RepeatAfterHours = 24,
        [int]$GapAlertMinutes = 0,                        # 0 = no downtime detection
        [string]$OkMessage = "",                          # message key to send on every success
        [hashtable]$Vars = @{}
    )
    try {
        $now = Get-Date
        $keys = @("firstFail", "lastAlert", "lastOk", "lastRun")
        $st = @{ lastError = "" }
        foreach ($k in $keys) { $st[$k] = $null }
        if (Test-Path $StateFile) {
            $raw = Get-Content $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($k in $keys) { if ($raw.$k) { $st[$k] = [datetime]$raw.$k } }
            if ($raw.lastError) { $st.lastError = "$($raw.lastError)" }
        }
        $fmt = "dd'/'MM'/'yyyy HH:mm"   # quoted: "/" alone means the culture's date separator
        $taskName = $Task
        try { $n = (Get-NotifyMessages).tasks.$Task; if ($n) { $taskName = $n } } catch {}
        $v = @{ env = $EnvName; task = $taskName; now = $now.ToString($fmt); log = $LogPath }
        foreach ($k in $Vars.Keys) { $v[$k] = $Vars[$k] }

        if ($GapAlertMinutes -gt 0 -and $st.lastRun -and ($now - $st.lastRun).TotalMinutes -ge $GapAlertMinutes) {
            $boot = Get-LastBootTime
            $gv = $v.Clone()
            $gv.from = $st.lastRun.ToString($fmt)
            $gv.to = $now.ToString($fmt)
            $gv.duration = Format-NotifyDuration ($now - $st.lastRun)
            $causeKey = if ($boot -and $boot -gt $st.lastRun) { "downtime_reboot" } else { "downtime_noreboot" }
            $gv.boot = if ($boot) { $boot.ToString($fmt) } else { "?" }
            $gv.cause = Get-NotifyText $causeKey $gv
            Send-Notify (Get-NotifyText "downtime" $gv) | Out-Null
        }
        $st.lastRun = $now

        if ($Ok) {
            if ($st.firstFail) {
                $v.since = $st.firstFail.ToString($fmt)
                $v.duration = Format-NotifyDuration ($now - $st.firstFail)
                if ($st.lastAlert) {
                    Send-Notify (Get-NotifyText "recovered" $v) | Out-Null
                } elseif (($now - $st.firstFail).TotalMinutes -ge $AlertAfterMinutes) {
                    $v.reason = (Get-ErrorExplanation $st.lastError).reason
                    Send-Notify (Get-NotifyText "recovered_unreported" $v) | Out-Null
                }
            }
            if ($OkMessage -and -not $st.lastAlert) { Send-Notify (Get-NotifyText $OkMessage $v) | Out-Null }
            $st.firstFail = $null; $st.lastAlert = $null; $st.lastOk = $now; $st.lastError = ""
        } else {
            if (-not $st.firstFail) { $st.firstFail = $now }
            $st.lastError = $Detail
            $failingMin = ($now - $st.firstFail).TotalMinutes
            $due = if ($st.lastAlert) { ($now - $st.lastAlert).TotalHours -ge $RepeatAfterHours }
                   else { $failingMin -ge $AlertAfterMinutes }
            if ($due) {
                $ex = Get-ErrorExplanation $Detail
                $rawShort = if ($Detail.Length -gt 400) { $Detail.Substring(0, 400) + " ..." } else { $Detail }
                $v.since = $st.firstFail.ToString($fmt)
                $v.last_ok = if ($st.lastOk) { $st.lastOk.ToString($fmt) } else {
                    try { (Get-NotifyMessages).unknown_time } catch { "?" } }
                $v.reason = $ex.reason; $v.fix = $ex.fix; $v.raw = $rawShort.Trim()
                if (Send-Notify (Get-NotifyText "failing" $v)) { $st.lastAlert = $now }
            }
        }
        $out = [ordered]@{}
        foreach ($k in $keys) { $out[$k] = if ($st[$k]) { $st[$k].ToString("o") } else { $null } }
        $out.lastError = $st.lastError
        $out | ConvertTo-Json | Out-File -FilePath $StateFile -Encoding utf8
    } catch {
        Log "WARN" "health state update failed: $($_.Exception.Message)"
    }
}