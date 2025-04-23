#!/bin/bash
# quick_fix_aibuddy.sh - Quick fix for AIBuddy with Chaotic AUR installed llama-cpp

set -e # Exit on any error

# Constants
INSTALL_DIR="$HOME/aibuddy"
CONFIG_DIR="$HOME/.config/aibuddy"
MODEL_PATH="/home/katana/projects/linux/aibuddy/agentica-org_DeepScaleR-1.5B-Preview-Q8_0.gguf"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== AIBuddy Quick Fix for Chaotic AUR ===${NC}"

# Check for llama-server
LLAMA_SERVER_PATH=""

# Check common locations
for possible_path in "/usr/bin/llama-server" "/usr/local/bin/llama-server" "/opt/llama-cpp/bin/llama-server"; do
    if [ -f "$possible_path" ] && [ -x "$possible_path" ]; then
        LLAMA_SERVER_PATH="$possible_path"
        echo -e "${GREEN}Found llama-server at: $LLAMA_SERVER_PATH${NC}"
        break
    fi
done

# If not found directly, try which
if [ -z "$LLAMA_SERVER_PATH" ]; then
    if command -v llama-server &> /dev/null; then
        LLAMA_SERVER_PATH=$(which llama-server)
        echo -e "${GREEN}Found llama-server in PATH: $LLAMA_SERVER_PATH${NC}"
    else
        echo -e "${RED}Error: llama-server not found. Please make sure the chaotic-aur package is installed:${NC}"
        echo -e "${YELLOW}pacman -Qs llama-cpp${NC}"
        exit 1
    fi
fi

# Create necessary directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"

# Save the server path for aibuddy to use
echo "LLAMA_SERVER=\"$LLAMA_SERVER_PATH\"" > "$INSTALL_DIR/server_path"
echo -e "${GREEN}Server path saved to: $INSTALL_DIR/server_path${NC}"

# Check if model exists
if [ ! -f "$MODEL_PATH" ]; then
    echo -e "${RED}Model not found at $MODEL_PATH.${NC}"
    read -p "Enter the full path to your GGUF model file: " custom_model_path
    if [ -f "$custom_model_path" ]; then
        MODEL_PATH="$custom_model_path"
        echo -e "${GREEN}Using model at $MODEL_PATH${NC}"
    else
        echo -e "${RED}Model file not found. Exiting.${NC}"
        exit 1
    fi
fi

# Create/update config
cat > "$CONFIG_DIR/config.json" << EOF
{
    "model_path": "$MODEL_PATH",
    "server_host": "localhost",
    "server_port": 8080,
    "context_length": 4096,
    "thread_count": 4,
    "temperature": 0.2,
    "max_tokens": 1024
}
EOF

echo -e "${GREEN}Configuration created at: $CONFIG_DIR/config.json${NC}"
echo -e "${YELLOW}If you've already installed aibuddy, try restarting the server:${NC}"
echo -e "aibuddy server --restart"
echo
echo -e "${GREEN}If not installed yet, please run setup_aibuddy.sh to complete installation${NC}"
