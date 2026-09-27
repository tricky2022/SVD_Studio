@echo off
REM Build a one-file Windows exe with icon into Releases/
setlocal
cd /d %~dp0
if not exist Releases mkdir Releases
.\.venv\Scripts\python -m pip install -q pyinstaller pillow
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean --distpath Releases SVDStudio.spec
echo.
echo Done. See Releases\SVDStudio.exe
endlocal
