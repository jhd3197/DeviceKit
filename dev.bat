@echo off
REM DeviceKit - Start backend and frontend in dev mode

REM Add ADB to PATH if not already available
where adb >nul 2>nul
if errorlevel 1 (
    if exist "C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe" (
        set "PATH=%PATH%;C:\Program Files (x86)\Android\android-sdk\platform-tools"
    ) else if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" (
        set "PATH=%PATH%;%LOCALAPPDATA%\Android\Sdk\platform-tools"
    )
)

echo Starting DeviceKit dev servers...
echo.
echo   Backend  : http://localhost:5050
echo   Frontend : http://localhost:5173
echo.

REM Start backend in a new window
start "DeviceKit API" cmd /k "cd /d %~dp0backend && python app.py"

REM Wait a moment for backend to initialize
timeout /t 2 /nobreak >nul

REM Start frontend in a new window
start "DeviceKit Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo Both servers started in separate windows.
echo Close those windows to stop the servers.
