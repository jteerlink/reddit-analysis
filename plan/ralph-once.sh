#!/bin/bash

# ralph-once.sh - Human-in-the-loop Ralph (JSON format)
# Run this manually to watch Claude work on one task at a time
# Usage: ./ralph-once.sh

claude --permission-mode acceptEdits "@PRD.md @progress.txt \
1. Read the JSON PRD and find a task where 'passes': false. \
2. Implement that task completely, following all steps. \
3. Run tests if they exist. \
4. Update PRD.md to set 'passes': true for the completed task. \
5. Append to progress.txt with what you did (include task category). \
6. Commit your changes with a clear message. \
ONLY DO ONE TASK AT A TIME."
