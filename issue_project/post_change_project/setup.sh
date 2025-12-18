#!/bin/bash
# Minimal setup: create venv and install requirements
python -m venv .venv || exit 0
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "Setup complete. Activate with: source .venv/bin/activate"