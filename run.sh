#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

BOT_PATTERN="python main\.py"
PIDFILE="bot.pid"

bot_pids() {
    pgrep -f "$BOT_PATTERN" 2>/dev/null || true
}

is_running() {
    [ -n "$(bot_pids)" ]
}

cmd_start() {
    if is_running; then
        echo "Bot is already running (PID: $(bot_pids | tr '\n' ' '))"
        echo "Stop it first with:  ./run.sh stop"
        exit 1
    fi
    rm -f "$PIDFILE"
    echo "Starting CPD Track bot (Ctrl-C to stop)…"
    # Write this wrapper's PID as a convenience hint for ./run.sh stop.
    echo "$$" > "$PIDFILE"
    trap 'rm -f "$PIDFILE"' EXIT INT TERM
    pixi run start
}

cmd_stop() {
    pids="$(bot_pids)"
    if [ -n "$pids" ]; then
        echo "Stopping bot (PID: $(echo "$pids" | tr '\n' ' '))…"
        # Kill the python process and any pixi wrapper that spawned it.
        pkill -f "$BOT_PATTERN" 2>/dev/null || true
        pkill -f "pixi run start" 2>/dev/null || true
        sleep 1
        rm -f "$PIDFILE"
        echo "Stopped."
        pids2="$(bot_pids)"
        [ -n "$pids2" ] && echo "Still running: $pids2" || true
    else
        rm -f "$PIDFILE"
        echo "No running bot found."
    fi
}

case "${1:-start}" in
  start|run) cmd_start ;;
  stop)      cmd_stop ;;
  status)    if is_running; then echo "Running (PID: $(bot_pids | tr '\n' ' '))"; else echo "Not running."; fi ;;
  test)      echo "No test suite configured; use: ./run.sh lint" ;;
  lint)      exec pixi run lint ;;
  shell)     exec pixi shell ;;
  install)   exec pixi install ;;
  *)
    cat <<'EOF'
Usage: ./run.sh [command]

Commands:
  start   (default) Run the Telegram bot
  stop    Stop a running bot
  status  Show whether the bot is running
  lint    Compile-check all Python files
  shell   Open an interactive shell inside the pixi environment
  install Install the pixi environment (first time / after deps change)
EOF
    ;;
esac