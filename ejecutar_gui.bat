@echo off
setlocal

cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m ig_orchestrator gui
) else (
    python -m ig_orchestrator gui
)

endlocal
