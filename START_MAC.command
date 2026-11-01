#!/bin/bash
cd "$(dirname "$0")" || exit 1
echo "Starting MA Trend Lab..."
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then
    echo "Python 3.11 or newer is required."
    echo "Install Python from python.org, then double-click START_MAC.command again."
    read -r -p "Press Return to close..."
    exit 1
fi
python3 bootstrap.py
status=$?
if [ "$status" -ne 0 ]; then
    echo "The app could not start. The error is shown above."
    read -r -p "Press Return to close..."
fi
exit "$status"
