#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  LinkedIn SDR Agent — Daily Pipeline Runner (Linux/Mac)
#  Run via cron or manually
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/data/logs"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/pipeline_$TODAY.log"

# Create logs directory
mkdir -p "$LOG_DIR"

# Activate virtual environment if it exists
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
elif [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
fi

# Load .env if it exists
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Run the pipeline
cd "$PROJECT_DIR"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting daily pipeline..." >> "$LOG_FILE"
python -m pipeline.daily_run --min-score 70 >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pipeline completed successfully." >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pipeline failed with exit code $EXIT_CODE." >> "$LOG_FILE"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done." >> "$LOG_FILE"
exit $EXIT_CODE
