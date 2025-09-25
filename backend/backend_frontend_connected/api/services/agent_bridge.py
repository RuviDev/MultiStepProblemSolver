# api/services/agent_bridge.py
import os, json, pathlib, subprocess
from typing import Tuple, Dict, Any

def _ensure_dirs(p: pathlib.Path):
    p.parent.mkdir(parents=True, exist_ok=True)

def compute_paths(chat_id: str):
    cfg_dir = os.getenv("AGENT_CONFIG_DIR", "agent8/config")
    state_base = pathlib.Path(os.getenv("AGENT_STATE_BASE", "agent8/state/chats"))
    out_base = pathlib.Path(os.getenv("AGENT_OUT_BASE", "agent8/out/chats"))
    py = os.getenv("PYTHON_EXEC", "python")
    state_path = state_base / f"{chat_id}.json"
    out_dir = out_base / chat_id
    out_path = out_dir / "request_envelope.json"
    return cfg_dir, state_path, out_dir, out_path, py

def _run_subprocess(cfg_dir: str, state_path: pathlib.Path, out_path: pathlib.Path, prompt: str, py: str):
    cmd = [
        py, "agent8/main.py",
        "--config_dir", str(cfg_dir),
        "--state_path", str(state_path),
        "--out", str(out_path),
        "--prompt", prompt
    ]
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise RuntimeError(f"Agent error: {cp.stderr or cp.stdout}")

def run_turn(chat_id: str, prompt: str) -> Tuple[str, Dict[str, Any], Dict[str, Any], Dict[str, str]]:
    mode = os.getenv("AGENT_RUN_MODE", "subprocess").lower()
    cfg_dir, state_path, out_dir, out_path, py = compute_paths(chat_id)

    _ensure_dirs(state_path)
    _ensure_dirs(out_path)

    if mode == "inproc":
        try:
            # Try in-process first
            from agent8.turn_api import run_turn as turn
            final_md, final_json, req_env = turn(prompt, str(cfg_dir), str(state_path), str(out_path))
            return final_md, final_json, req_env, {"state_path": str(state_path), "out_dir": str(out_dir)}
        except Exception as e:
            # Graceful fallback to subprocess so user is never blocked by import quirks
            _run_subprocess(cfg_dir, state_path, out_path, prompt, py)

    elif mode == "subprocess":
        _run_subprocess(cfg_dir, state_path, out_path, prompt, py)
    else:
        # Unknown mode: fall back to subprocess
        _run_subprocess(cfg_dir, state_path, out_path, prompt, py)

    # Common tail: read artifacts
    final_md = (out_dir / "final_response.md").read_text(encoding="utf-8", errors="ignore")
    final_json = json.loads((out_dir / "final_response.json").read_text(encoding="utf-8"))
    req_env = json.loads((out_dir / "request_envelope.json").read_text(encoding="utf-8"))
    return final_md, final_json, req_env, {"state_path": str(state_path), "out_dir": str(out_dir)}
