#!/usr/bin/env bash

set -e  

# Set environment
python3 -m venv .venv

# Make the environment the default one
echo "source .venv/bin/activate" >> ~/.bashrc

# Activate the environment
source .venv/bin/activate

# Install requirements
pip3 install -r requirements.txt