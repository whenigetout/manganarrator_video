@echo off
title MangaNarrator Studio - Backend (API, publishing, built frontend)
echo Backend console: FastAPI, the publishing worker and the built React app.
echo Press Ctrl+C in this window to stop the backend.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_studio.ps1" -NoBrowser -AccessLog -Title "MangaNarrator Studio - Backend (API + publishing)"
if errorlevel 1 (
  echo.
  echo The backend stopped with an error. Review the messages above.
  pause
)
