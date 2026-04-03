#!/bin/bash

# afk-ralph.sh - Automated Ralph loop (JSON format)
# Run this and go make coffee. Claude will work through the PRD.
# Usage: ./afk-ralph.sh <iterations>

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <iterations>"
  echo "Example: $0 20"
  exit 1
fi

MAX_ITERATIONS=$1

for ((i=1; i<=MAX_ITERATIONS; i++)); do
  echo "=== Iteration $i/$MAX_ITERATIONS ==="
  
  result=$(docker sandbox run claude --permission-mode acceptEdits -p "@PRD.md @progress.txt \
1. Read the JSON PRD array and find the first task where 'passes': false. \
2. Implement that task completely, following all steps. \
3. Run tests and type checks if they exist. \
4. Update PRD.md to set 'passes': true for the completed task. \
5. Append to progress.txt with timestamp and task category completed. \
6. Commit your changes with a descriptive message. \
ONLY WORK ON A SINGLE TASK PER ITERATION. \
If all tasks have 'passes': true, output <promise>COMPLETE</promise>.")

  echo "$result"
  
  # Check for completion signal
  if [[ "$result" == *"<promise>COMPLETE</promise>"* ]]; then
    echo ""
    echo "✅ All PRD tasks complete after $i iterations!"
    exit 0
  fi
  
  # Brief pause between iterations
  sleep 2
done

echo ""
echo "⚠️  Reached max iterations ($MAX_ITERATIONS) without completion."
echo "   Check progress.txt and PRD.md to see what's done."
