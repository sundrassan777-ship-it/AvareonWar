@echo off
echo ==========================================
echo   AvareonWar - Dependency Installer
echo ==========================================
echo.

:: Try to find Python
where python >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python
    goto :found
)
where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=py
    goto :found
)

echo ERROR: Python is not installed or not on PATH.
echo.
echo Please install Python from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found
echo Found Python:
%PYTHON% --version
echo.
echo Installing game dependencies...
echo.
%PYTHON% -m pip install -r requirements.txt
echo.
if %errorlevel%==0 (
    echo ==========================================
    echo   All dependencies installed successfully!
    echo   Run the game with: %PYTHON% main.py
    echo ==========================================
) else (
    echo ==========================================
    echo   Some dependencies failed to install.
    echo   Try running as administrator.
    echo ==========================================
)
echo.
pause
