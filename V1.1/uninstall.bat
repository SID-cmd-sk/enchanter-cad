@echo off
REM ============================================================================
REM  ENCHANTER-CAD 2D  --  UNINSTALLER (run as Administrator)
REM  Right-click -> "Run as administrator".
REM ============================================================================
setlocal
set APPDIR=%ProgramFiles%\ENCHANTER-CAD 2D

echo Removing ENCHANTER-CAD 2D ...
if exist "%APPDIR%" rmdir /s /q "%APPDIR%"

set DT=%PUBLIC%\Desktop
if not exist "%DT%" set DT=%USERPROFILE%\Desktop
if exist "%DT%\ENCHANTER-CAD 2D.lnk" del /f /q "%DT%\ENCHANTER-CAD 2D.lnk"

set SM=%ProgramData%\Microsoft\Windows\Start Menu\Programs
if exist "%SM%\ENCHANTER-CAD 2D" rmdir /s /q "%SM%\ENCHANTER-CAD 2D"

reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /f >nul 2>nul

echo Done. ENCHANTER-CAD 2D removed.
pause
endlocal
