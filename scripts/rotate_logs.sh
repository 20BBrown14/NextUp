#!/bin/sh
set -e

LOG_DIR="/config/log"
CURRENT_LOG="${LOG_DIR}/NextUp.log"
OLD_LOG="${LOG_DIR}/NextUp.log.1"

# Ensure the log directory exists
mkdir -p "$LOG_DIR"

# Delete NextUp.log.1 if it exists
if [ -f "$OLD_LOG" ]; then
  rm -f "$OLD_LOG"
fi

# Move NextUp.log to NextUp.log.1 if it exists
if [ -f "$CURRENT_LOG" ]; then
  mv "$CURRENT_LOG" "$OLD_LOG"
fi

# Return the log path for CMD
echo "$CURRENT_LOG"