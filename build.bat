@echo off
echo ====================================
echo  file_care EXE 빌드
echo ====================================

pip install -r requirements.txt

pyinstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name "file_care" ^
  --add-data "settings.json;." ^
  app.py

echo.
echo ====================================
echo  빌드 완료: dist\file_care.exe
echo ====================================
pause
