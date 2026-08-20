#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
STREAMLIT_BIN="$SCRIPT_DIR/.venv/bin/streamlit"
OLLAMA_BIN="$SCRIPT_DIR/tools/Ollama.app/Contents/Resources/ollama"
OLLAMA_LOG="$SCRIPT_DIR/storage/ollama.log"
export OLLAMA_MODELS="$SCRIPT_DIR/ollama_models"
export OLLAMA_HOST="127.0.0.1:11434"

if [[ ! -x "$PYTHON_BIN" || ! -x "$STREAMLIT_BIN" ]]; then
    echo "The macOS virtual environment is missing. Run: python3 -m venv .venv"
    exit 1
fi

if [[ ! -x "$OLLAMA_BIN" ]]; then
    echo "The project-local Ollama runtime is missing at: $OLLAMA_BIN"
    exit 1
fi

mkdir -p "$SCRIPT_DIR/storage" "$OLLAMA_MODELS"

if ! curl --silent --fail "http://$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
    echo "Starting project-local Ollama..."
    "$OLLAMA_BIN" serve >"$OLLAMA_LOG" 2>&1 &

    for _ in {1..45}; do
        if curl --silent --fail "http://$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
fi

if ! curl --silent --fail "http://$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
    echo "Ollama did not start. Check $OLLAMA_LOG"
    exit 1
fi

if ! "$OLLAMA_BIN" list | grep '^qwen2.5:3b' >/dev/null; then
    echo "qwen2.5:3b is not present in $OLLAMA_MODELS"
    echo "Run: OLLAMA_MODELS=\"$OLLAMA_MODELS\" \"$OLLAMA_BIN\" pull qwen2.5:3b"
    exit 1
fi

echo "Ollama and qwen2.5:3b are ready. Starting Canopy from $SCRIPT_DIR"
exec "$STREAMLIT_BIN" run app.py --server.address 127.0.0.1 --server.port 8501
