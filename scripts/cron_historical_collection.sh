#!/bin/bash
# Cron script for Reddit Historical Data Collection
# This script runs every 2 days via cron

# Exit on any error
set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/cron_collection.log"
ERROR_LOG="$LOG_DIR/cron_collection_errors.log"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Function to log messages
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1" | tee -a "$ERROR_LOG" "$LOG_FILE"
}

# Function to check if collection is already running
is_running() {
    pgrep -f "reddit_api.cli historical" > /dev/null 2>&1
}

# Function to check if collection was run recently (within last 24 hours)
was_recently_run() {
    if [ -f "$LOG_FILE" ]; then
        # Check if there's a successful run in the last 24 hours
        if grep -q "Historical collection completed successfully" "$LOG_FILE"; then
            last_success=$(grep "Historical collection completed successfully" "$LOG_FILE" | tail -1 | cut -d' ' -f1-2)
            if [ -n "$last_success" ]; then
                last_timestamp=$(date -d "$last_success" +%s 2>/dev/null || date -j -f "%Y-%m-%d %H:%M:%S" "$last_success" +%s 2>/dev/null)
                current_timestamp=$(date +%s)
                time_diff=$((current_timestamp - last_timestamp))
                
                # If less than 24 hours (86400 seconds), skip
                if [ $time_diff -lt 86400 ]; then
                    return 0  # True - was recently run
                fi
            fi
        fi
    fi
    return 1  # False - was not recently run
}

# Main execution
main() {
    log "Starting Reddit historical collection cron job"
    
    # Check if already running
    if is_running; then
        log_error "Collection already running, skipping this execution"
        exit 1
    fi
    
    # Check if was recently run
    if was_recently_run; then
        log "Collection was run recently, skipping this execution"
        exit 0
    fi
    
    # Change to project directory
    cd "$PROJECT_ROOT" || {
        log_error "Failed to change to project directory: $PROJECT_ROOT"
        exit 1
    }
    
    # Check if uv is available
    if ! command -v uv >/dev/null 2>&1; then
        log_error "uv command not found. Please install uv or ensure it's in PATH"
        exit 1
    fi
    
    # Check if the reddit_api module is available
    if ! uv run python -c "import reddit_api" >/dev/null 2>&1; then
        log_error "reddit_api module not found. Please ensure the project is properly set up"
        exit 1
    fi
    
    # Run the collection command
    log "Executing: uv run python -m reddit_api.cli historical --days 2 --posts 150 --comments 50"
    
    if uv run python -m reddit_api.cli historical --days 2 --posts 150 --comments 50 >> "$LOG_FILE" 2>> "$ERROR_LOG"; then
        log "Historical collection completed successfully"
        exit 0
    else
        log_error "Historical collection failed"
        exit 1
    fi
}

# Run main function
main "$@"
