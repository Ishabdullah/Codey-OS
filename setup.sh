#!/usr/bin/env bash
#
# Quick setup for Codey-V3 - adds to PATH
#
# Run this if you've already installed dependencies
# and just need to make codeyOS available system-wide.
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
chmod +x "$CODEY_V2_DIR/codeyOS"
chmod +x "$CODEY_V2_DIR/codeydOS"

# Add to PATH if not already there
if ! grep -q "codeyOS" "$SHELL_CONFIG" 2>/dev/null; then
    echo "" >> "$SHELL_CONFIG"
    echo "# Codey-V3" >> "$SHELL_CONFIG"
    echo "export PATH=\"$CODEY_V2_DIR:\$PATH\"" >> "$SHELL_CONFIG"
    echo "Added codeyOS to PATH in $SHELL_CONFIG"
else
    echo "codeyOS already in PATH"
fi

# Source the config
source "$SHELL_CONFIG"

# Create daemon directory
mkdir -p "$HOME/.codeyOS"

echo ""
echo "Setup complete!"
echo ""
echo "Now you can use Codey-V3:"
echo "  codeydOS start          # Start the daemon"
echo "  codeyOS \"hello\"         # Send a task"
echo "  codeyOS status          # Check status"
echo ""
