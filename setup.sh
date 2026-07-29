#!/data/data/com.termux/files/usr/bin/bash
#
# Quick setup for Codey-OS - adds to PATH
#
# Run this if you've already installed dependencies
# and just need to make codeyOS available system-wide.
#

CODEY_OS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Determine shell config
if [ -n "$BASH_VERSION" ]; then
    SHELL_CONFIG="$HOME/.bashrc"
elif [ -n "$ZSH_VERSION" ]; then
    SHELL_CONFIG="$HOME/.zshrc"
else
    SHELL_CONFIG="$HOME/.bashrc"
fi

# Make scripts executable
chmod +x "$CODEY_OS_DIR/codeyOS"
chmod +x "$CODEY_OS_DIR/codeydOS"

# Add to PATH if not already there
if ! grep -q "codeyOS" "$SHELL_CONFIG" 2>/dev/null; then
    echo "" >> "$SHELL_CONFIG"
    echo "# Codey-OS" >> "$SHELL_CONFIG"
    echo "export PATH=\"$CODEY_OS_DIR:\$PATH\"" >> "$SHELL_CONFIG"
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
echo "Now you can use Codey-OS:"
echo "  codeydOS start          # Start the daemon"
echo "  codeyOS \"hello\"         # Send a task"
echo "  codeyOS status          # Check status"
echo ""
