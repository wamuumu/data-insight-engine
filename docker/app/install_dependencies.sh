#!/usr/bin/env bash

set -e

# Install system dependencies
apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*
