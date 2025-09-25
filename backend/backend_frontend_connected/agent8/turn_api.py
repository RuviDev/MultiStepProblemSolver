# agent8/turn_api.py
import sys, os, json, pathlib, importlib

def run_turn(prompt: str, cfg_dir: str, state_path: str, out_path: str):
    """
    Run the agent's CLI entrypoint *inside* this Python process.
    We patch sys.path so that 'agent' (which lives at agent8/agent) is importable.
    """
    agent8_dir = pathlib.Path(__file__).parent.resolve()        # .../agent8
    project_root = agent8_dir.parent.resolve()                  # project root

    # Ensure both 'agent8' (this pkg) and 'agent' (subpkg) are importable.
    # - 'agent' is a top-level package inside agent8 (agent8/agent)
    #   so we need agent8_dir on sys.path.
    if str(agent8_dir) not in sys.path:
        sys.path.insert(0, str(agent8_dir))
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Make sure target folders exist
    out_dir = pathlib.Path(out_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    pathlib.Path(state_path).parent.mkdir(parents=True, exist_ok=True)

    # Build argv exactly like the CLI
    argv = [
        "agent8/main.py",
        "--config_dir", str(cfg_dir),
        "--state_path", str(state_path),
        "--out", str(out_path),
        "--prompt", prompt,
    ]

    # Import the CLI entrypoint only after sys.path is set
    old_argv = sys.argv
    try:
        sys.argv = argv
        mod = importlib.import_module("agent8.main")
        cli_main = getattr(mod, "main")
        cli_main()
    finally:
        sys.argv = old_argv

    # Read the outputs the CLI always writes
    final_md = (out_dir / "final_response.md").read_text(encoding="utf-8")
    final_json = json.loads((out_dir / "final_response.json").read_text(encoding="utf-8"))
    req_env = json.loads((out_dir / "request_envelope.json").read_text(encoding="utf-8"))
    return final_md, final_json, req_env
