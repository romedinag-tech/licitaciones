@echo off
REM Procesa las bases descargadas y abre el analizador local.
cd /d "%~dp0"
python analizar_bases.py
echo.
echo Si no se abrio solo, busca "Analizador de Bases.html" en tu carpeta de licitaciones.
pause
