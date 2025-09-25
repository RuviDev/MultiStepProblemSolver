param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Prompt)
$promptText = ($Prompt -join " ")
if (Test-Path .venv\Scripts\Activate.ps1) { . .\.venv\Scripts\Activate.ps1 }
python agent8/main.py --config_dir agent8/config --state_path agent8/state/thread_state.json --out agent8/out/request_envelope.json --prompt "$promptText"
