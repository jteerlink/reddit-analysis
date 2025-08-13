# Reddit Historical Collection Scheduler

This document explains how to set up automated scheduling for the Reddit historical data collection to run every 2 days.

## 🎯 Overview

The scheduling system provides multiple options to automatically run the Reddit historical collection command:

```bash
uv run python -m reddit_api.cli historical --days 2 --posts 150 --comments 50
```

## 🚀 Quick Setup

### Option 1: Interactive Setup (Recommended)

Run the interactive setup script to choose your preferred method:

```bash
# Make the setup script executable
chmod +x scripts/setup_scheduler.sh

# Run the interactive setup
./scripts/setup_scheduler.sh
```

This will guide you through choosing and configuring your preferred scheduling method.

## 📋 Available Scheduling Methods

### 1. Python Scheduler (Recommended for Development)

**Best for**: Development, testing, and when you want full control over the scheduling logic.

**Features**:
- Cross-platform compatibility
- Built-in logging and error handling
- Configurable scheduling times
- Backup run support
- Easy to modify and extend

**Setup**:
```bash
# Make executable
chmod +x scripts/schedule_historical_collection.py

# Run once immediately
python scripts/schedule_historical_collection.py --run-now

# Run in foreground (press Ctrl+C to stop)
python scripts/schedule_historical_collection.py

# Run in background (daemon mode)
nohup python scripts/schedule_historical_collection.py --daemon > /dev/null 2>&1 &
```

**Usage Options**:
- `--run-now`: Execute collection immediately and exit
- `--daemon`: Run in background mode
- `--project-root`: Specify custom project root path

### 2. Cron Scheduler (Unix/Linux/macOS)

**Best for**: Production systems, servers, and when you want system-level scheduling.

**Features**:
- System-level scheduling
- Automatic restart on system reboot
- Standard Unix tooling
- Lightweight and reliable

**Setup**:
```bash
# Make executable
chmod +x scripts/cron_historical_collection.sh

# Add to your crontab (every 2 days at 2:00 AM)
crontab -e

# Add this line:
0 2 */2 * * /path/to/reddit-analyzer/scripts/cron_historical_collection.sh
```

**Cron Expression**: `0 2 */2 * *` means:
- `0` - At minute 0
- `2` - At 2 AM
- `*/2` - Every 2 days
- `*` - Every month
- `*` - Every day of week

### 3. macOS LaunchAgent

**Best for**: macOS users who want native system integration.

**Features**:
- Native macOS integration
- Automatic startup on login
- System-level management
- Clean integration with macOS

**Setup**:
```bash
# Make the shell script executable
chmod +x scripts/cron_historical_collection.sh

# Run the setup script and choose option 3
./scripts/setup_scheduler.sh
```

**Manual Setup**:
```bash
# Copy plist to LaunchAgents
cp scripts/com.reddit.analyzer.historical.plist ~/Library/LaunchAgents/

# Update paths in the plist file
sed -i.bak "s|/Users/jaredteerlink/repos/reddit-analyzer|$(pwd)|g" ~/Library/LaunchAgents/com.reddit.analyzer.historical.plist

# Load the LaunchAgent
launchctl load ~/Library/LaunchAgents/com.reddit.analyzer.historical.plist
```

## ⚙️ Configuration

### Scheduling Parameters

All methods run the collection every 2 days with these parameters:
- **Days**: 2 (collects data from the last 2 days)
- **Posts**: 150 per subreddit
- **Comments**: 50 per post
- **Time**: 2:00 AM (configurable)

### Logging

All scheduling methods create logs in the `logs/` directory:
- `scheduler.log` - General execution logs
- `cron_collection.log` - Collection execution logs
- `cron_collection_errors.log` - Error logs
- `launchagent_stdout.log` - LaunchAgent stdout (macOS)
- `launchagent_stderr.log` - LaunchAgent stderr (macOS)

## 🔧 Customization

### Modifying Collection Parameters

To change the collection parameters, edit the respective script:

**Python Scheduler** (`scripts/schedule_historical_collection.py`):
```python
cmd = [
    "uv", "run", "python", "-m", "reddit_api.cli", "historical",
    "--days", "2",           # Change this value
    "--posts", "150",        # Change this value
    "--comments", "50"       # Change this value
]
```

**Cron/LaunchAgent** (`scripts/cron_historical_collection.sh`):
```bash
uv run python -m reddit_api.cli historical --days 2 --posts 150 --comments 50
```

### Changing Schedule Frequency

**Python Scheduler**: Modify the `schedule_job()` method:
```python
# Change from every 2 days to every day
schedule.every().day.at("02:00").do(self.run_collection)

# Change from every 2 days to every week
schedule.every().week.at("02:00").do(self.run_collection)
```

**Cron**: Modify the cron expression:
```bash
# Every day at 2:00 AM
0 2 * * * /path/to/script.sh

# Every week on Sunday at 2:00 AM
0 2 * * 0 /path/to/script.sh

# Every month on the 1st at 2:00 AM
0 2 1 * * /path/to/script.sh
```

**LaunchAgent**: Edit the plist file to modify `StartCalendarInterval`.

## 🧪 Testing

### Test the Collection Command

Before setting up scheduling, test that the collection works:

```bash
# Test using the setup script
./scripts/setup_scheduler.sh
# Choose option 4: Test Collection Command

# Or test manually
./scripts/cron_historical_collection.sh
```

### Test the Scheduler

**Python Scheduler**:
```bash
# Test immediate execution
python scripts/schedule_historical_collection.py --run-now

# Test scheduling (will run at next scheduled time)
python scripts/schedule_historical_collection.py
```

**Cron**: Check your crontab:
```bash
crontab -l
```

**LaunchAgent**: Check status:
```bash
launchctl list | grep reddit
```

## 📊 Monitoring

### Check Scheduler Status

```bash
# Using the setup script
./scripts/setup_scheduler.sh
# Choose option 5: Show Status

# Check logs manually
tail -f logs/scheduler.log
tail -f logs/cron_collection.log
```

### Monitor Collection Process

```bash
# Check if collection is running
pgrep -f "reddit_api.cli historical"

# View running processes
ps aux | grep "reddit_api.cli historical"
```

### View Recent Logs

```bash
# Last 10 log entries
tail -10 logs/cron_collection.log

# Follow logs in real-time
tail -f logs/cron_collection.log

# Search for errors
grep "ERROR" logs/cron_collection.log
```

## 🚨 Troubleshooting

### Common Issues

**1. Collection Fails**
- Check if `uv` is available: `which uv`
- Verify the project is set up: `uv run python -c "import reddit_api"`
- Check logs for specific error messages

**2. Scheduler Not Running**
- Verify the script is executable: `ls -la scripts/schedule_historical_collection.py`
- Check if the process is running: `pgrep -f "schedule_historical_collection"`
- Review system logs for errors

**3. Cron Not Working**
- Check crontab: `crontab -l`
- Verify cron service is running: `sudo service cron status` (Linux) or `sudo launchctl list | grep cron` (macOS)
- Check system logs: `tail -f /var/log/syslog` (Linux) or `log show --predicate 'process == "cron"'` (macOS)

**4. LaunchAgent Issues**
- Check if loaded: `launchctl list | grep reddit`
- Verify plist syntax: `plutil -lint ~/Library/LaunchAgents/com.reddit.analyzer.historical.plist`
- Check system logs: `log show --predicate 'process == "launchd"'`

### Debug Mode

**Python Scheduler**: Add debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Shell Scripts**: Add debug output:
```bash
set -x  # Print commands as they execute
```

## 🔄 Maintenance

### Updating the Scheduler

When you update the project:

1. **Stop the scheduler**:
   - Python: `pkill -f "schedule_historical_collection"`
   - Cron: `crontab -e` and comment out the line
   - LaunchAgent: `launchctl unload ~/Library/LaunchAgents/com.reddit.analyzer.historical.plist`

2. **Update the code**

3. **Restart the scheduler** using the setup script

### Log Rotation

Consider setting up log rotation to prevent logs from growing too large:

```bash
# Add to crontab for weekly log rotation
0 1 * * 0 find logs/ -name "*.log" -mtime +7 -exec gzip {} \;
```

## 📚 Additional Resources

- [Historical Collection Documentation](historical-collection.md)
- [Reddit API Module README](../README_reddit_module.md)
- [Project README](../README.md)
- [Example Scripts](../example_historical_collection.py)

## 🤝 Support

If you encounter issues:

1. Check the logs in the `logs/` directory
2. Verify your system meets the prerequisites
3. Test the collection command manually
4. Review this documentation for troubleshooting steps

For persistent issues, check the project's issue tracker or create a new issue with:
- Your operating system and version
- The scheduling method you're using
- Relevant log output
- Steps to reproduce the issue
