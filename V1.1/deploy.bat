@echo off
REM ============================================================================
REM  ENCHANTER-CAD 2D  --  INSTALLER (run as Administrator)
REM
REM  Right-click this file -> "Run as administrator".
REM  It copies the self-contained build to:
REM      C:\Program Files\ENCHANTER-CAD 2D\
REM  creates a Desktop + Start Menu shortcut, and registers the app in
REM  Control Panel > Programs and Features.
REM
REM  To UNINSTALL: delete the folder and run the registry cleanup below,
REM  or use the Inno Setup installer (installer\ENCHANTR-CAD.iss).
REM ============================================================================
setlocal
cd /d "%~dp0"

set APPDIR=%ProgramFiles%\ENCHANTER-CAD 2D
set SRC=%~dp0dist\ENCHANTER-CAD
set EXE=%APPDIR%\ENCHANTER-CAD.exe
set ICON=%APPDIR%\_internal\assets\icons\appicon.ico

if not exist "%SRC%" (
    echo ERROR: %SRC% not found. Run build\build_exe.bat first.
    pause
    exit /b 1
)

echo Installing ENCHANTER-CAD 2D to "%APPDIR%" ...
if exist "%APPDIR%" rmdir /s /q "%APPDIR%"
xcopy "%SRC%" "%APPDIR%\" /E /I /Q /Y >nul

REM Desktop shortcut
set DT=%PUBLIC%\Desktop
if not exist "%DT%" set DT=%USERPROFILE%\Desktop
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%DT%\ENCHANTER-CAD 2D.lnk'); $s.TargetPath='%EXE%'; $s.WorkingDirectory='%APPDIR%'; $s.IconLocation='%ICON%,0'; $s.Save()"

REM Start Menu shortcut
set SM=%ProgramData%\Microsoft\Windows\Start Menu\Programs
if not exist "%SM%\ENCHANTER-CAD 2D" mkdir "%SM%\ENCHANTER-CAD 2D"
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%SM%\ENCHANTER-CAD 2D\ENCHANTER-CAD 2D.lnk'); $s.TargetPath='%EXE%'; $s.WorkingDirectory='%APPDIR%'; $s.IconLocation='%ICON%,0'; $s.Save()"

REM Control Panel registration
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /v DisplayName /t REG_SZ /d "ENCHANTER-CAD 2D" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /v DisplayVersion /t REG_SZ /d "1.1" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /v Publisher /t REG_SZ /d "Enchantr" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /v InstallLocation /t REG_SZ /d "%APPDIR%" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /v DisplayIcon /t REG_SZ /d "%ICON%,0" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /v UninstallString /t REG_SZ /d "\"%EXE%\" --uninstall" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /v URLInfoAbout /t REG_SZ /d "https://sidharth-kr.pages.dev" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /v NoModify /t REG_DWORD /d 1 /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ENCHANTER-CAD2D" /v NoRepair /t REG_DWORD /d 1 /f >nul

echo.
echo ============================================================
echo  ENCHANTER-CAD 2D installed successfully.
echo  Location: %APPDIR%
echo  Launch from the Desktop or Start Menu shortcut.
echo ============================================================
pause
endlocal
