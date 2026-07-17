@echo off
REM Doble clic para descargar los antecedentes de las licitaciones del radar.
REM Se abre una ventana de Chrome mientras baja los archivos; no la cierres.
cd /d "%~dp0"
python descargar_antecedentes.py %*
echo.
echo ----------------------------------------------------
echo Listo. Revisa la carpeta "Antecedentes Licitaciones".
pause
