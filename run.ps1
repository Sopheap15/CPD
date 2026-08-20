param([string]$Command = "start")

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Get-BotProcesses {
    # Match only this project's bot (by its pixi python path + main.py), so it
    # never touches the Clerkship bot or any other python process.
    $marker = Join-Path $ProjectRoot ".pixi"
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object {
            $_.CommandLine -match 'main\.py' -and
            $_.CommandLine -like "*$marker*"
        }
}

function Start-Bot {
    $running = Get-BotProcesses
    if ($running) {
        Write-Host "Bot is already running (PID: $($running.ProcessId -join ', '))"
        Write-Host "Stop it first with:  .\run.ps1 stop"
        exit 1
    }
    Write-Host "Starting CPD Track bot (Ctrl-C to stop)..."
    pixi run start
}

function Stop-Bot {
    $running = Get-BotProcesses
    if ($running) {
        Write-Host "Stopping bot (PID: $($running.ProcessId -join ', '))..."
        $running | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
        Write-Host "Stopped."
    } else {
        Write-Host "No running bot found."
    }
}

function Status-Bot {
    $running = Get-BotProcesses
    if ($running) {
        Write-Host "Running (PID: $($running.ProcessId -join ', '))"
    } else {
        Write-Host "Not running."
    }
}

switch ($Command) {
    { $_ -in @("start", "run") } { Start-Bot }
    "stop"                       { Stop-Bot }
    "status"                     { Status-Bot }
    "lint"                       { pixi run lint }
    "shell"                      { pixi shell }
    "install"                    { pixi install }
    default {
        Write-Host @"
Usage: .\run.ps1 [command]

Commands:
  start   (default) Run the Telegram bot
  stop    Stop a running bot
  status  Show whether the bot is running
  lint    Compile-check all Python files
  shell   Open an interactive shell inside the pixi environment
  install Install the pixi environment (first time / after deps change)
"@
    }
}
