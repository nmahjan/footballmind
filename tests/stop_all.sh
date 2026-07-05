#!/bin/bash
# stop_all.sh — Kill all benchmark servers

echo "🛑 Stopping all benchmark servers..."

for port in 8080 8081 8082 8083 8084 8085 8090; do
  lsof -ti :$port | xargs kill -9 2>/dev/null
  echo "  Stopped port $port"
done

echo ""
echo "✅ All servers stopped."
