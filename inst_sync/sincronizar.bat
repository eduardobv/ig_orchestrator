@echo off
setlocal

rem Doble clic en la instancia: copia lo que cambio en el PC principal. Detén el batch antes.
rem Ruta del PC principal: inst_sync\origen.txt (una linea).
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
