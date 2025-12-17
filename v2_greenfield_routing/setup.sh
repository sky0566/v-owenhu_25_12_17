#!/bin/bash
# Setup script for v2 greenfield routing service (Linux/macOS)

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

echo "Setup complete!"
echo "To activate: source .venv/bin/activate"
echo "To run tests: pytest"
