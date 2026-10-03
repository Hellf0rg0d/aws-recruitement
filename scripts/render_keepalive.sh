#!/bin/bash
# ==============================================================================
# Render Keepalive Ping Script
# Pings health check endpoint to prevent cloud instance spin-down
# ==============================================================================

LOG_FILE="$HOME/.render_keepalive.log"
TARGET_URL="${RENDER_HEALTH_URL:-https://your-app.onrender.com/health}"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

# Perform HTTP GET request with max 30s timeout
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}\nTIME_TOTAL:%{time_total}s" -m 30 "$TARGET_URL")
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d':' -f2)
TIME_TOTAL=$(echo "$RESPONSE" | grep "TIME_TOTAL:" | cut -d':' -f2)

if [ "$HTTP_STATUS" = "200" ]; then
    echo "[$TIMESTAMP] SUCCESS (200 OK) in ${TIME_TOTAL} - Render is awake" >> "$LOG_FILE"
else
    echo "[$TIMESTAMP] WARNING (Status: $HTTP_STATUS) in ${TIME_TOTAL}" >> "$LOG_FILE"
fi

# Keep only the last 500 lines of log to prevent file growth
if [ -f "$LOG_FILE" ]; then
    tail -n 500 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi
