#!/usr/bin/env bash
#
# Quick setup for Codey-V3 - adds to PATH
#
# Run this if you've already installed dependencies
# and just need to make codey3 available system-wide.
#

CODEY_V2_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Determine shell config
if [ -n "$BASH_VERSION" ]; then
    SHELL_CONFIG="$HOME/.bashrc"
elif [ -n "$ZSH_VERSION" ]; then
    SHELL_CONFIG="$HOME/.zshrc"
else
    SHELL_CONFIG="$HOME/.bashrc"
fi

# Make scripts executable
chmod +x "$CODEY_V2_DIR/codey3"
chmod +x "$CODEY_V2_DIR/codeyd2"

# Add to PATH if not already there
if ! grep -q "codey-v3" "$SHELL_CONFIG" 2>/dev/null; then
    echo "" >> "$SHELL_CONFIG"
    echo "# Codey-V3" >> "$SHELL_CONFIG"
    echo "export PATH=\"$CODEY_V2_DIR:\$PATH\"" >> "$SHELL_CONFIG"
    echo "Added codey3 to PATH in $SHELL_CONFIG"
else
    echo "codey3 already in PATH"
fi

# Source the config
source "$SHELL_CONFIG"

# Create daemon directory
mkdir -p "$HOME/.codey-v3"

echo ""
echo "Setup complete!"
echo ""
echo "Now you can use Codey-V3:"
echo "  codeyd2 start          # Start the daemon"
echo "  codey3 \"hello\"         # Send a task"
echo "  codey3 status          # Check status"
echo ""
