#!/usr/bin/env bash
set -euo pipefail
# Activate venv if present
if [ -f ".venv/bin/activate" ]; then source .venv/bin/activate; fi
python agent8/main.py   --config_dir agent8/config   --state_path agent8/state/thread_state.json   --out agent8/out/request_envelope.json   --prompt "$*"
