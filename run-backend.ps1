$ErrorActionPreference='Stop'
$python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if(-not $env:PARASPARA_AI_MODE){$env:PARASPARA_AI_MODE='strands'}
if(-not $env:PARASPARA_MODEL_ID){$env:PARASPARA_MODEL_ID='global.amazon.nova-2-lite-v1:0'}
if(-not $env:AWS_REGION){$env:AWS_REGION='us-east-1'}
$env:PYTHONIOENCODING='utf-8'
if(-not (Test-Path -LiteralPath $python)){ throw 'Run: py -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt' }
& $python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765


