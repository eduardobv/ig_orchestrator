@echo off
setlocal

cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

set "BATCH_ID="
set /p "BATCH_ID=Introduce el batch ID y pulsa Enter: "

if not defined BATCH_ID (
    echo No se ha introducido ningun batch ID. No se ejecutara nada.
    goto :end
)

echo(%BATCH_ID%| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo El batch ID debe ser un numero entero.
    goto :end
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m ig_orchestrator run_continue --batch-id %BATCH_ID%
) else (
    python -m ig_orchestrator run_continue --batch-id %BATCH_ID%
)

:end
endlocal
