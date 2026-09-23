@echo off
rem Builds dist\GravSim.exe - a single file you can share; no Python needed to run it.
rem Run from this folder:  build_exe.bat
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller -r requirements.txt || goto :error
python -m PyInstaller --noconfirm --clean --onefile --windowed --name GravSim main.py || goto :error
echo.
echo Done: dist\GravSim.exe
goto :eof
:error
echo Build failed.
exit /b 1
