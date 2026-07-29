#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO_NAME="Codey-OS"
GITHUB_USER="Ishabdullah"
REMOTE_URL="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
BRANCH="main"

if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  echo "Git not initialized. Running git init..."
  git init -b "$BRANCH"
else
  echo "Git already initialized."
fi

if command -v gh &>/dev/null; then
  echo "gh CLI found. Creating public repo and pushing..."
  gh repo create "$REPO_NAME" --public --source=. --remote=origin --push
else
  echo "gh CLI not found. Manual steps:"
  echo ""
  echo "  git remote add origin $REMOTE_URL"
  echo "  git add ."
  echo "  git commit -m 'Initial commit for Codey-OS'"
  echo "  git push -u origin $BRANCH"
  echo ""
  echo "Running them now..."
  git remote add origin "$REMOTE_URL" 2>/dev/null || true
  git add .
  git commit -m "Initial commit for Codey-OS"
  git push -u origin "$BRANCH"
fi

echo "Done."
