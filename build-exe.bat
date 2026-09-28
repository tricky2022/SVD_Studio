@echo off
REM Build the Windows executables into Releases\ (GUI + CLI/MCP console).
REM   Releases\SVDStudio.exe       GUI (also answers --cli / --mcp)
REM   Releases\svdstudio-cli.exe   console build for CLI and MCP clients
setlocal
cd /d %~dp0
if not exist Releases mkdir Releases

.\.venv\Scripts\python -m pip install -q pyinstaller pillow || goto :fail

REM the .ico is a build input; regenerate it so the exe never loses its icon
.\.venv\Scripts\python tools\make_icon.py || goto :fail

if exist build rmdir /s /q build
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean --distpath Releases SVDStudio.spec || goto :fail

echo.
echo Verifying the icon and version resource were embedded...
.\.venv\Scripts\python tools\verify_exe.py || goto :fail

echo.
echo Done:
dir /b Releases\*.exe
endlocal
exit /b 0

:fail
echo.
echo BUILD FAILED (exit code %errorlevel%)
endlocal
exit /b 1
