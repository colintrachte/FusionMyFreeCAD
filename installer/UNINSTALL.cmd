@echo off
setlocal
title Uninstall FusionMyFreeCAD
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall-FusionMyFreeCAD.ps1"
set "UNINSTALL_EXIT=%ERRORLEVEL%"
echo.
if not "%UNINSTALL_EXIT%"=="0" echo Rollback did not complete. Read the error above.
pause
exit /b %UNINSTALL_EXIT%
