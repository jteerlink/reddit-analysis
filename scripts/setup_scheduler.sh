#!/bin/bash
# Setup script for Reddit Historical Collection Scheduler
# This script helps you choose and configure your preferred scheduling method

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Function to check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check if we're in the right directory
    if [ ! -f "$PROJECT_ROOT/pyproject.toml" ]; then
        print_error "This script must be run from the reddit-analyzer project directory"
        exit 1
    fi
    
    # Check if uv is available
    if ! command -v uv >/dev/null 2>&1; then
        print_error "uv command not found. Please install uv first:"
        echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    
    # Check if the reddit_api module is available
    if ! uv run python -c "import reddit_api" >/dev/null 2>&1; then
        print_error "reddit_api module not found. Please ensure the project is properly set up"
        exit 1
    fi
    
    print_status "All prerequisites met!"
}

# Function to create logs directory
setup_logs() {
    print_header "Setting up Logs Directory"
    
    mkdir -p "$LOGS_DIR"
    print_status "Logs directory created: $LOGS_DIR"
}

# Function to setup Python scheduler
setup_python_scheduler() {
    print_header "Setting up Python Scheduler"
    
    # Make the script executable
    chmod +x "$SCRIPT_DIR/schedule_historical_collection.py"
    
    print_status "Python scheduler script is ready!"
    echo ""
    echo "Usage options:"
    echo "  1. Run once immediately:"
    echo "     python scripts/schedule_historical_collection.py --run-now"
    echo ""
    echo "  2. Run in foreground (press Ctrl+C to stop):"
    echo "     python scripts/schedule_historical_collection.py"
    echo ""
    echo "  3. Run in background (daemon mode):"
    echo "     nohup python scripts/schedule_historical_collection.py --daemon > /dev/null 2>&1 &"
    echo ""
    echo "  4. Run with systemd (Linux) or create a service"
}

# Function to setup cron scheduler
setup_cron_scheduler() {
    print_header "Setting up Cron Scheduler"
    
    # Make the script executable
    chmod +x "$SCRIPT_DIR/cron_historical_collection.sh"
    
    # Get current user's crontab
    CURRENT_CRON=$(crontab -l 2>/dev/null || echo "")
    
    # Check if cron job already exists
    if echo "$CURRENT_CRON" | grep -q "cron_historical_collection.sh"; then
        print_warning "Cron job already exists!"
        echo "Current crontab:"
        echo "$CURRENT_CRON"
    else
        # Create new cron entry (every 2 days at 2:00 AM)
        CRON_ENTRY="0 2 */2 * * $SCRIPT_DIR/cron_historical_collection.sh"
        
        # Add to crontab
        (echo "$CURRENT_CRON"; echo "$CRON_ENTRY") | crontab -
        
        print_status "Cron job added successfully!"
        echo "Cron entry: $CRON_ENTRY"
    fi
    
    echo ""
    echo "To view your crontab: crontab -l"
    echo "To edit your crontab: crontab -e"
    echo "To remove all cron jobs: crontab -r"
}

# Function to setup macOS LaunchAgent
setup_launchagent() {
    print_header "Setting up macOS LaunchAgent"
    
    # Make the shell script executable
    chmod +x "$SCRIPT_DIR/cron_historical_collection.sh"
    
    # Copy plist to LaunchAgents directory
    LAUNCHAGENTS_DIR="$HOME/Library/LaunchAgents"
    PLIST_NAME="com.reddit.analyzer.historical.plist"
    
    mkdir -p "$LAUNCHAGENTS_DIR"
    cp "$SCRIPT_DIR/$PLIST_NAME" "$LAUNCHAGENTS_DIR/"
    
    # Update the plist with correct paths
    sed -i.bak "s|/Users/jaredteerlink/repos/reddit-analyzer|$PROJECT_ROOT|g" "$LAUNCHAGENTS_DIR/$PLIST_NAME"
    rm "$LAUNCHAGENTS_DIR/$PLIST_NAME.bak"
    
    # Load the LaunchAgent
    launchctl load "$LAUNCHAGENTS_DIR/$PLIST_NAME"
    
    print_status "LaunchAgent setup complete!"
    echo ""
    echo "LaunchAgent file: $LAUNCHAGENTS_DIR/$PLIST_NAME"
    echo ""
    echo "To manage the LaunchAgent:"
    echo "  - Start: launchctl start com.reddit.analyzer.historical"
    echo "  - Stop: launchctl stop com.reddit.analyzer.historical"
    echo "  - Unload: launchctl unload $LAUNCHAGENTS_DIR/$PLIST_NAME"
    echo "  - View status: launchctl list | grep reddit"
}

# Function to test the collection
test_collection() {
    print_header "Testing Collection Command"
    
    print_status "Running test collection..."
    
    if "$SCRIPT_DIR/cron_historical_collection.sh"; then
        print_status "Test collection successful!"
    else
        print_error "Test collection failed. Check the logs for details."
        echo "Log file: $LOGS_DIR/cron_collection.log"
        echo "Error log: $LOGS_DIR/cron_collection_errors.log"
    fi
}

# Function to show status
show_status() {
    print_header "Scheduler Status"
    
    echo "Project root: $PROJECT_ROOT"
    echo "Logs directory: $LOGS_DIR"
    echo ""
    
    # Check if any collection processes are running
    if pgrep -f "reddit_api.cli historical" > /dev/null 2>&1; then
        print_status "Collection process is currently running"
        pgrep -f "reddit_api.cli historical" | xargs ps -o pid,command
    else
        print_warning "No collection process currently running"
    fi
    
    echo ""
    
    # Check recent logs
    if [ -f "$LOGS_DIR/cron_collection.log" ]; then
        echo "Recent log entries:"
        tail -5 "$LOGS_DIR/cron_collection.log"
    else
        print_warning "No log file found"
    fi
}

# Function to show main menu
show_menu() {
    clear
    print_header "Reddit Historical Collection Scheduler Setup"
    echo ""
    echo "Choose an option:"
    echo ""
    echo "1. Setup Python Scheduler (recommended for development)"
    echo "2. Setup Cron Scheduler (Unix/Linux/macOS)"
    echo "3. Setup macOS LaunchAgent (macOS only)"
    echo "4. Test Collection Command"
    echo "5. Show Status"
    echo "6. Exit"
    echo ""
    read -p "Enter your choice (1-6): " choice
    
    case $choice in
        1)
            setup_python_scheduler
            ;;
        2)
            setup_cron_scheduler
            ;;
        3)
            if [[ "$OSTYPE" == "darwin"* ]]; then
                setup_launchagent
            else
                print_error "LaunchAgent is only available on macOS"
            fi
            ;;
        4)
            test_collection
            ;;
        5)
            show_status
            ;;
        6)
            print_status "Goodbye!"
            exit 0
            ;;
        *)
            print_error "Invalid choice. Please try again."
            ;;
    esac
    
    echo ""
    read -p "Press Enter to continue..."
    show_menu
}

# Main execution
main() {
    print_header "Reddit Historical Collection Scheduler"
    echo "This script will help you set up automated collection every 2 days"
    echo ""
    
    # Check prerequisites
    check_prerequisites
    
    # Setup logs directory
    setup_logs
    
    # Show menu
    show_menu
}

# Run main function
main "$@"
