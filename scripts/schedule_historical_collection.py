#!/usr/bin/env python3
"""
Scheduled Reddit Historical Data Collection

This script runs the Reddit historical collection command every 2 days.
It can be run as a standalone script or as a system service.

Usage:
    python scripts/schedule_historical_collection.py
    python scripts/schedule_historical_collection.py --daemon
    python scripts/schedule_historical_collection.py --run-now
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add the src directory to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    import schedule
except ImportError:
    print("Installing required dependency: schedule")
    subprocess.run([sys.executable, "-m", "pip", "install", "schedule"], check=True)
    import schedule


class HistoricalCollectionScheduler:
    """Scheduler for running Reddit historical data collection every 2 days."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.logger = self._setup_logging()
        self.last_run: Optional[datetime] = None
        self.run_count = 0
        
    def _setup_logging(self) -> logging.Logger:
        """Set up logging configuration."""
        log_dir = self.project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        logger = logging.getLogger("historical_scheduler")
        logger.setLevel(logging.INFO)
        
        # File handler
        file_handler = logging.FileHandler(log_dir / "scheduler.log")
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def run_collection(self) -> bool:
        """Run the historical collection command."""
        try:
            self.logger.info("Starting historical Reddit data collection...")
            
            # Change to project directory
            os.chdir(self.project_root)
            
            # Run the collection command
            cmd = [
                "uv", "run", "python", "-m", "reddit_api.cli", "historical",
                "--days", "2",
                "--posts", "150", 
                "--comments", "50"
            ]
            
            self.logger.info(f"Executing: {' '.join(cmd)}")
            
            # Run the command and capture output
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode == 0:
                self.logger.info("Historical collection completed successfully")
                self.logger.info(f"STDOUT: {result.stdout}")
                self.last_run = datetime.now()
                self.run_count += 1
                return True
            else:
                self.logger.error(f"Historical collection failed with return code {result.returncode}")
                self.logger.error(f"STDERR: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("Historical collection timed out after 1 hour")
            return False
        except Exception as e:
            self.logger.error(f"Error running historical collection: {e}")
            return False
    
    def schedule_job(self):
        """Schedule the job to run every 2 days."""
        # Schedule to run every 2 days at 2:00 AM
        schedule.every(2).days.at("02:00").do(self.run_collection)
        
        # Also schedule a backup run at 2:00 PM in case the morning run fails
        schedule.every(2).days.at("14:00").do(self._backup_run)
        
        self.logger.info("Scheduled historical collection every 2 days at 2:00 AM and 2:00 PM")
    
    def _backup_run(self):
        """Backup run that only executes if the main run hasn't succeeded today."""
        if (self.last_run is None or 
            datetime.now().date() > self.last_run.date()):
            self.logger.info("Executing backup collection run")
            self.run_collection()
        else:
            self.logger.info("Skipping backup run - main run already completed today")
    
    def run_scheduler(self, daemon: bool = False):
        """Run the scheduler loop."""
        self.schedule_job()
        
        if daemon:
            self.logger.info("Starting scheduler in daemon mode...")
        else:
            self.logger.info("Starting scheduler (press Ctrl+C to stop)...")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
                
                # Log status every hour
                if datetime.now().minute == 0:
                    self.logger.info(f"Scheduler running - Last run: {self.last_run}, Total runs: {self.run_count}")
                    
        except KeyboardInterrupt:
            self.logger.info("Scheduler stopped by user")
        except Exception as e:
            self.logger.error(f"Scheduler error: {e}")
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Schedule Reddit historical data collection every 2 days"
    )
    parser.add_argument(
        "--daemon", 
        action="store_true",
        help="Run in daemon mode (continuous background execution)"
    )
    parser.add_argument(
        "--run-now",
        action="store_true", 
        help="Run collection immediately and exit"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Path to project root directory"
    )
    
    args = parser.parse_args()
    
    # Initialize scheduler
    scheduler = HistoricalCollectionScheduler(args.project_root)
    
    if args.run_now:
        # Run collection immediately
        success = scheduler.run_collection()
        sys.exit(0 if success else 1)
    else:
        # Run scheduler
        scheduler.run_scheduler(daemon=args.daemon)


if __name__ == "__main__":
    main()
