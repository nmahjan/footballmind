#!/bin/bash
# start_all.sh — Launch all 6 benchmark servers + the switcher dashboard
# Usage: bash start_all.sh
# Stop all: bash stop_all.sh

BASE="$(cd "$(dirname "$0")" && pwd)"

echo "🏀 Starting AI Benchmark Servers..."
echo ""

# Kill anything already on these ports
for port in 8080 8081 8082 8083 8084 8085 8090; do
  lsof -ti :$port | xargs kill -9 2>/dev/null
done

# Start each server in background
echo "▶ BMAD v4        → http://127.0.0.1:8080"
cd "$BASE/bmadv4_imp" && python app.py > /tmp/bmad_v4.log 2>&1 &

echo "▶ Traycer.ai     → http://127.0.0.1:8081"
cd "$BASE/traycer_imp" && python app.py > /tmp/traycer.log 2>&1 &

echo "▶ Amp            → http://127.0.0.1:8082"
cd "$BASE/amp_imp" && python app.py > /tmp/amp.log 2>&1 &

echo "▶ Superpowers    → http://127.0.0.1:8083"
cd "$BASE/superpower_imp" && python app.py > /tmp/superpowers.log 2>&1 &

echo "▶ Ralph          → http://127.0.0.1:8084"
cd "$BASE/ralph_imp" && python app.py > /tmp/ralph.log 2>&1 &

echo "▶ BMAD v6        → http://127.0.0.1:8085"
cd "$BASE/bmadv6" && python app.py > /tmp/bmadv6.log 2>&1 &

# Small delay then start switcher
sleep 2
echo ""
echo "▶ Switcher       → http://127.0.0.1:8090"
cd "$BASE" && python switcher/app.py > /tmp/switcher.log 2>&1 &

sleep 1
echo ""
echo "✅ All servers started!"
echo "🌐 Open the dashboard: http://127.0.0.1:8090"
echo ""
echo "To stop all servers: bash stop_all.sh"
