#!/bin/bash

set -e

echo "=== Git & GitHub Setup Script ==="

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "[*] Git not initialized. Running git init..."
    git init
else
    echo "[*] Git already initialized."
fi

# Check if gh CLI is installed
if command -v gh &> /dev/null; then
    echo "[*] gh CLI found. Creating public repo and pushing..."
    gh repo create Codey-V3 --public --source=. --remote=origin --push
else
    echo "[*] gh CLI not found. Printing manual commands..."
    echo ""
    echo "Run the following commands manually:"
    echo ""
    echo "  git remote add origin https://github.com/Ishabdullah/Codey-V3.git"
    echo "  git add ."
    echo "  git commit -m 'Initial commit for Codey-V3'"
    echo "  git branch -M main"
    echo "  git push -u origin main"
    echo ""
fi
