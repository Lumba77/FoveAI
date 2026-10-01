#!/bin/bash
set -e

echo "=== Installing git and git-lfs via apt ==="
apt-get update -y
apt-get install -y git git-lfs

echo "=== Setting up global git config for user lumba ==="
sudo -u lumba git config --global user.name "Lumba77"
sudo -u lumba git config --global user.email "Lumba77@users.noreply.github.com"
sudo -u lumba git config --global init.defaultBranch main
sudo -u lumba git config --global --add safe.directory /home/lumba/FoveAI

echo "=== Git setup complete ==="
git --version
