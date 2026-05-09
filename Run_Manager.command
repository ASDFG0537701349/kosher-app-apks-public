#!/bin/bash
# MacOS Runner for Private Store Manager

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "🚀 Starting Private Store Manager..."

# Check if Python is installed
if ! command -v python3 &> /dev/null
then
    echo "❌ Python 3 was not found. Please install it from python.org"
    read -p "Press enter to exit"
    exit
fi

# Install dependencies if missing
echo "📦 Checking dependencies..."
python3 -m pip install pyaxmlparser pillow google-play-scraper &> /dev/null

# Run the unified manager
python3 tools/unified_manager.py
