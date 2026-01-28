@echo off
REM DeviceKit - Start backend and frontend in dev mode

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
