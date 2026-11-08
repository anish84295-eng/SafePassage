Set-Location (Join-Path $PSScriptRoot '..\backend')
& .\.venv\Scripts\python.exe -m uvicorn safepassage.api.main:app --app-dir src --reload --reload-dir src
