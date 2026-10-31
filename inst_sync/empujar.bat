@echo off
setlocal

rem PARTE 1, en el PC principal: copia el codigo a la instancia (ruta en inst_sync\destino.txt).
rem Detén el batch de la instancia antes. Al final avisa si hay que ejecutar sincronizar.bat en la instancia.
cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" inst_sync\sync.py --empujar %*
) else (
    python inst_sync\sync.py --empujar %*
)

echo.
pause
endlocal
exit /b
