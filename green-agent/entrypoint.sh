#!/bin/bash
set -e

echo "=== Downloading benchmark datasets ==="

# Download MiniWoB++ HTML files (if not already present)
MINIWOB_DIR="/home/agent/datasets/miniwob/html/miniwob"
if [ -d "$MINIWOB_DIR" ] && [ "$(ls -A $MINIWOB_DIR/*.html 2>/dev/null)" ]; then
    echo "MiniWoB++ already downloaded, skipping."
else
    echo "Downloading MiniWoB++ from GitHub..."
    TEMP_DIR="/tmp/miniwob_clone"
    rm -rf "$TEMP_DIR"
    git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/Farama-Foundation/miniwob-plusplus.git "$TEMP_DIR"
    cd "$TEMP_DIR" && git sparse-checkout set miniwob/html && cd /home/agent
    mkdir -p /home/agent/datasets/miniwob
    cp -r "$TEMP_DIR/miniwob/html" /home/agent/datasets/miniwob/
    rm -rf "$TEMP_DIR"
    echo "MiniWoB++ downloaded successfully."
fi

# Download WebLINX metadata (if not already present)
WEBLINX_META="/home/agent/datasets/weblinx/metadata.json"
if [ -f "$WEBLINX_META" ]; then
    echo "WebLINX metadata already downloaded, skipping."
else
    echo "Downloading WebLINX metadata from HuggingFace (~106MB)..."
    uv run python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='McGill-NLP/weblinx-browsergym',
    repo_type='dataset',
    filename='metadata.json',
    local_dir='datasets/weblinx'
)
"
    echo "WebLINX metadata downloaded successfully."
fi

echo "=== Dataset setup complete ==="

# Run the agent with all passed arguments
exec uv run python -m src.main "$@"
