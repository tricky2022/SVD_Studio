@echo off
REM Build the Windows executables into Releases\ (GUI + console CLI).
setlocal
cd /d %~dp0
if not exist Releases mkdir Releases

.\.venv\Scripts\python -m pip install -q -e ".[excel,release]" || goto :fail
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean --distpath Releases SVDStudio.spec || goto :fail

echo.
Releases\svdstudio-cli.exe --version || goto :fail

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
