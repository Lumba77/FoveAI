#!/bin/bash
set -e

echo "=== 1. Installing Node.js and npm via apt ==="
apt-get update -y
apt-get install -y nodejs npm

echo "=== 2. Enabling systemd user lingering for user lumba ==="
loginctl enable-linger lumba

echo "=== Node.js setup complete ==="
node --version
npm --version
