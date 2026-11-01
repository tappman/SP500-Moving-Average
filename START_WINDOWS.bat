@echo off
setlocal
cd /d "%~dp0"
echo Starting MA Trend Lab...
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 bootstrap.py
    if errorlevel 1 goto failed
    exit /b 0
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
    python bootstrap.py
    if errorlevel 1 goto failed
    exit /b 0
)
echo.
echo Python 3.11 or newer is required.
echo Install Python from python.org and enable "Add Python to PATH".
echo Then double-click START_WINDOWS.bat again.
pause
exit /b 1
:failed
echo.
echo The app could not start. The error is shown above.
echo Check your Internet connection if dependency installation failed.
pause
exit /b 1
