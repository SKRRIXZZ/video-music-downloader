@echo off
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul
if not errorlevel 1 set "PY=py"

%PY% -m PyInstaller --version >nul 2>nul
if errorlevel 1 %PY% -m pip install --upgrade pyinstaller

%PY% -c "import pystray, PIL" >nul 2>nul
if errorlevel 1 %PY% -m pip install --upgrade pystray Pillow

%PY% -c "import yt_dlp" >nul 2>nul
if errorlevel 1 %PY% -m pip install --upgrade yt-dlp

set "ICON="
if exist icon.ico set "ICON=--icon=icon.ico"

set "FFMPEG="
if exist ffmpeg.exe set "FFMPEG=--add-binary ffmpeg.exe;."

%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name=VideoDownloader %ICON% %FFMPEG% --hidden-import=pystray._win32 --hidden-import=PIL._tkinter_finder --hidden-import=yt_dlp --collect-all pystray --collect-all PIL --collect-all yt_dlp video_downloader_multilang.pyw

echo.
echo DONE. See dist\VideoDownloader.exe
pause