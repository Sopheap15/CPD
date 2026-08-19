# Deploys the CPD Track Telegram bot to Cloudflare Workers WITHOUT Node.js.
#
# Uses only the Cloudflare REST API (PowerShell 5.1+ Invoke-RestMethod).
# It:
#   1. Creates/uses a KV namespace and uploads worker\data.json under key "data"
#   2. Uploads worker\entry.py as a Python Worker (webhook mode)
#   3. Stores TELEGRAM_BOT_TOKEN as a secret, COURSE_REGISTRATION_LINK/ADMIN_IDS as vars
#   4. Registers the worker's URL as the Telegram webhook
#
# Prerequisites:
#   - A Cloudflare account ID  (dashboard: right sidebar of the home page)
#   - An API token with permissions: "Workers Scripts: Edit" and "Workers KV Storage: Edit"
#     (My Profile -> API Tokens -> Create Token)
#   - .env with TELEGRAM_BOT_TOKEN set (auto-read if not passed)
#
# Usage:
#   .\deploy.ps1 -AccountId <YOUR_ACCOUNT_ID> -ApiToken <YOUR_TOKEN>
#   .\deploy.ps1 -AccountId <ID> -ApiToken <TOKEN> -AdminIds "123456789,987654321"
#
# To keep the polling bot running locally instead, call deleteWebhook (see
# DEPLOY_CLOUDFLARE.md) - a bot cannot use webhook and getUpdates at the same time.

param(
    [Parameter(Mandatory = $true)]
    [string]$AccountId,

    [Parameter(Mandatory = $true)]
    [string]$ApiToken,

    [string]$ScriptName = "cpd-track",

    [string]$NamespaceTitle = "cpd-track",

    [string]$NamespaceId = "",

    [string]$DataPath = "",

    [string]$EntryPath = "",

    [string]$TelegramToken = "",

    [string]$CourseLink = "",

    [string]$AdminIds = "",

    [switch]$SkipWebhook
)

$ErrorActionPreference = "Stop"

if (-not $DataPath) { $DataPath = Join-Path $PSScriptRoot "worker\data.json" }
if (-not $EntryPath) { $EntryPath = Join-Path $PSScriptRoot "worker\entry.py" }

# -------------------------------------------------------------- read .env
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path -LiteralPath $envFile) {
    Get-Content -LiteralPath $envFile | ForEach-Object {
        if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$') {
            $k = $Matches[1]
            $v = $Matches[2].Trim()
            if (-not $TelegramToken -and $k -eq "TELEGRAM_BOT_TOKEN") { $TelegramToken = $v }
            if (-not $CourseLink -and $k -eq "COURSE_REGISTRATION_LINK") { $CourseLink = $v }
            if (-not $AdminIds -and $k -eq "ADMIN_IDS") { $AdminIds = $v }
        }
    }
}

if (-not (Test-Path -LiteralPath $EntryPath)) { throw "Worker file not found: $EntryPath" }
if (-not (Test-Path -LiteralPath $DataPath)) { throw "Data file not found: $DataPath (run `pixi run export` first)" }
if (-not $TelegramToken) { throw "TELEGRAM_BOT_TOKEN is missing (set it in .env or pass -TelegramToken)" }

$CompatibilityDate = Get-Date -Format "yyyy-MM-dd"
$api = "https://api.cloudflare.com/client/v4/accounts/$AccountId"

function Invoke-CF {
    param($Method, $Uri, $Body = $null, $ContentType = "application/json")
    $headers = @{ Authorization = "Bearer $ApiToken" }
    $params = @{ Method = $Method; Uri = $Uri; Headers = $headers }
    if ($null -ne $Body) {
        $params.Body = $Body
        $params.ContentType = $ContentType
    }
    $resp = Invoke-RestMethod @params
    if (-not $resp.success) {
        throw "Cloudflare API error: $($resp | ConvertTo-Json -Depth 6 -Compress)"
    }
    return $resp
}

Write-Host "1/6 Ensure KV namespace '$NamespaceTitle'..."
$nsList = Invoke-CF -Method Get -Uri "$api/storage/kv/namespaces"
$ns = $nsList.result | Where-Object { $_.title -eq $NamespaceTitle } | Select-Object -First 1
if (-not $ns) {
    if ($NamespaceId) {
        $ns = @{ id = $NamespaceId }
    }
    else {
        $created = Invoke-CF -Method Post -Uri "$api/storage/kv/namespaces" -Body (@{ title = $NamespaceTitle } | ConvertTo-Json)
        $ns = $created.result
    }
}
$namespaceId = $ns.id
Write-Host "  KV namespace id: $namespaceId"

Write-Host "2/6 Uploading data.json to KV key 'data'..."
$dataBytes = [System.IO.File]::ReadAllBytes($DataPath)
Invoke-RestMethod -Method Put -Uri "$api/storage/kv/namespaces/$namespaceId/values/data" `
    -Headers @{ Authorization = "Bearer $ApiToken" } `
    -ContentType "application/octet-stream" `
    -Body $dataBytes | Out-Null
Write-Host "  uploaded $([math]::Round($dataBytes.Length / 1KB, 1)) KB"

Write-Host "3/6 Uploading Python Worker '$ScriptName'..."
$metadata = @{
    main_module          = "entry.py"
    compatibility_date   = $CompatibilityDate
    compatibility_flags  = @("python_workers")
    kv_namespaces        = @(@{ binding = "CPD_KV"; namespace_id = $namespaceId })
    vars                 = @{ COURSE_REGISTRATION_LINK = $CourseLink; ADMIN_IDS = $AdminIds }
} | ConvertTo-Json -Depth 6

$boundary = "----CPD-" + [guid]::NewGuid().ToString("N")
$utf8 = [System.Text.Encoding]::UTF8
$entryContent = [System.IO.File]::ReadAllText($EntryPath, $utf8)

$stream = New-Object System.IO.MemoryStream
function Add-MultipartPart {
    param($Name, $FileName, $ContentType, $Content, $Bytes = $null)
    $header = "--$boundary`r`nContent-Disposition: form-data; name=`"$Name`""
    if ($FileName) { $header += "; filename=`"$FileName`"" }
    $header += "`r`nContent-Type: $ContentType`r`n`r`n"
    $hb = $utf8.GetBytes($header)
    $stream.Write($hb, 0, $hb.Length)
    if ($null -ne $Bytes) {
        $stream.Write($Bytes, 0, $Bytes.Length)
    }
    else {
        $vb = $utf8.GetBytes([string]$Content)
        $stream.Write($vb, 0, $vb.Length)
    }
    $tail = $utf8.GetBytes("`r`n")
    $stream.Write($tail, 0, $tail.Length)
}
Add-MultipartPart -Name "metadata" -ContentType "application/json" -Content $metadata
Add-MultipartPart -Name "entry.py" -FileName "entry.py" -ContentType "text/x-python" -Content $entryContent
$end = $utf8.GetBytes("--$boundary--`r`n")
$stream.Write($end, 0, $end.Length)
$multipartBody = $stream.ToArray()

$resp = Invoke-RestMethod -Method Put -Uri "$api/workers/scripts/$ScriptName" `
    -Headers @{ Authorization = "Bearer $ApiToken" } `
    -ContentType "multipart/form-data; boundary=$boundary" `
    -Body $multipartBody
if (-not $resp.success) {
    throw "Worker upload failed: $($resp | ConvertTo-Json -Depth 6 -Compress)"
}
Write-Host "  worker uploaded (id $($resp.result.id))"

Write-Host "4/6 Storing TELEGRAM_BOT_TOKEN secret..."
Invoke-RestMethod -Method Put -Uri "$api/workers/scripts/$ScriptName/secrets" `
    -Headers @{ Authorization = "Bearer $ApiToken" } `
    -ContentType "application/json" `
    -Body (@{ name = "TELEGRAM_BOT_TOKEN"; text = $TelegramToken } | ConvertTo-Json) | Out-Null
Write-Host "  secret stored"

$workerUrl = ""
try {
    $sub = Invoke-CF -Method Get -Uri "$api/workers/subdomain"
    $workerUrl = "https://$ScriptName.$($sub.result.subdomain).workers.dev"
}
catch {
    Write-Warning "Could not determine workers.dev subdomain: $($_.Exception.Message)"
}

if ($workerUrl) {
    Write-Host "  Worker URL: $workerUrl"
    if (-not $SkipWebhook) {
        Write-Host "5/6 Setting Telegram webhook -> $workerUrl"
        $wh = Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$TelegramToken/setWebhook" `
            -ContentType "application/json" `
            -Body (@{
                url               = $workerUrl
                drop_pending_updates = $true
                allowed_updates   = @("message", "callback_query")
            } | ConvertTo-Json)
        if (-not $wh.ok) {
            throw "Telegram setWebhook failed: $($wh.description)"
        }
        Write-Host "  webhook set OK"
    }
    else {
        Write-Host "5/6 Skipping webhook (-SkipWebhook)"
    }
}

Write-Host "6/6 Verifying..."
$info = Invoke-RestMethod -Method Get -Uri "$api/workers/scripts/$ScriptName" -Headers @{ Authorization = "Bearer $ApiToken" }
Write-Host "  script: $ScriptName / main_module: $($info.result.default_environment.script.main_module)"

Write-Host ""
Write-Host "Done. Test the bot in Telegram: /start then /view <name>."
