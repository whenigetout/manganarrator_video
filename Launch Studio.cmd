@echo off
setlocal
title MangaNarrator Studio - backend + frontend in one server
echo MangaNarrator Audio Studio
echo Logs are also written to: %~dp0local_tmp\logs
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch_studio.ps1" %*
set "studio_exit=%ERRORLEVEL%"
if not "%studio_exit%"=="0" (
  echo.
  echo The studio launcher exited with code %studio_exit%.
  echo Review the messages above and the log file in %~dp0local_tmp\logs
  pause
)
endlocal
