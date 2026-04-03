# Ralph Wiggum Loop - Reddit Analyzer

This directory contains the Ralph loop setup for autonomous AI development.

## Files

- **PRD.md** — Product Requirements Document (what to build)
- **progress.txt** — Tracks completed work between iterations
- **ralph-once.sh** — Human-in-the-loop script (run one task at a time)
- **afk-ralph.sh** — Automated loop script (go AFK while Claude works)

## Quick Start

### 1. Generate or Write Your PRD

**Option A: Use Claude's plan mode (recommended)**
```bash
cd ~/repos/reddit-analyzer/plan
claude
# Press shift-tab to enter plan mode
# Describe what you want to build
# When happy with the plan, say: "Save this to PRD.md"
```

**Option B: Write PRD.md manually**
- List features as checkable tasks
- Be specific about requirements
- Define clear success criteria

### 2. Start with Human-in-the-Loop

Build intuition by running one iteration at a time:

```bash
./ralph-once.sh
# Watch what Claude does
# Check the commit
# Run again
```

### 3. Go AFK (when ready)

Run the automated loop:

```bash
./afk-ralph.sh 20
# Go make coffee
# Come back to working code
```

## How It Works

1. **Claude reads** PRD.md and progress.txt
2. **Picks next task** from the PRD autonomously
3. **Implements it** completely
4. **Commits the changes** with clear message
5. **Updates progress.txt** with what was done
6. **Repeats** until `<promise>COMPLETE</promise>` or max iterations

## Safety

- Max iterations prevents runaway costs
- Docker sandbox keeps work isolated
- One task per iteration = small, reviewable commits
- Git history shows exactly what happened when

## Tips

- Start with 10-20 iterations for first runs
- Review commits between runs to catch issues early
- Keep PRD tasks small and specific
- Update PRD.md if priorities change mid-loop

## Resources

- [Ralph Wiggum Technique](https://awesomeclaude.ai/ralph-wiggum)
- [Getting Started Guide](https://www.aihero.dev/getting-started-with-ralph)
- [11 Tips for AI Coding with Ralph](https://www.aihero.dev/tips-for-ai-coding-with-ralph-wiggum)
