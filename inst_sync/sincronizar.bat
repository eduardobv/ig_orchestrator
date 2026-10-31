@echo off
setlocal

rem PARTE 2, doble clic en la instancia (solo si el PC principal lo pide): dependencias, SQL y base.
rem Detén el batch antes. El codigo lo copia empujar.bat desde el PC principal.
cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" inst_sync\sync.py %*
) else (
    python inst_sync\sync.py %*
)

echo.
pause
endlocal
exit /b
