#!/usr/bin/env bash

set -e

# Install dependecies [if any]
apt-get update \
    && rm -rf /var/lib/apt/lists/*
