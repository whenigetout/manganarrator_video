@echo off
rem Compatibility entry point: both names now start the same Studio server.
call "%~dp0Launch Studio.cmd" %*
exit /b %ERRORLEVEL%
