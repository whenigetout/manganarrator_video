@echo off
title MangaNarrator Studio - Frontend (Vite dev server, port 5173)
cd /d "%~dp0..\frontend"
if errorlevel 1 (
  echo Could not open the frontend folder.
  pause
  exit /b 1
)
echo Frontend console: Vite dev server with hot reload on http://127.0.0.1:5173/
echo Press Ctrl+C in this window to stop it.
echo.
call npm.cmd run dev -- --port 5173 --strictPort
if errorlevel 1 (
  echo.
  echo The Vite dev server stopped with an error. Review the messages above.
  pause
)
