@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --icon=icon.ico --name=VideoDownloader "video_downloader_multilang.pyw"
echo.
echo Done: dist\VideoDownloader.exe
pause
