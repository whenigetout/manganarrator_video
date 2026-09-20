@echo off
setlocal
title MangaNarrator Studio - dev launcher
echo MangaNarrator Audio Studio - dev mode
echo This opens two console windows: backend and frontend.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch_studio_dev.ps1" %*
set "studio_exit=%ERRORLEVEL%"
if not "%studio_exit%"=="0" (
  echo.
  echo The dev launcher exited with code %studio_exit%. Review the messages above.
)
echo.
pause
endlocal
