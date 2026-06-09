#!/usr/bin/env bash

set -e

# Install curl dependency to check for conenction health
apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*