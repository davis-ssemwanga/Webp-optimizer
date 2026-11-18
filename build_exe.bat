@echo off
REM Builds dist\WebPOptimizer\WebPOptimizer.exe  (run from the project folder, venv activated)
pip install pyinstaller
set ICON=
if exist assets\icons\app.ico set ICON=--icon assets\icons\app.ico
pyinstaller --noconfirm --clean --windowed --name WebPOptimizer %ICON% --add-data "assets;assets" main.py
echo.
echo Done. Run dist\WebPOptimizer\WebPOptimizer.exe
pause
