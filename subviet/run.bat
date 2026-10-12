@echo off
title SubViet - Trich Xuat Phu De Tieng Viet Tu Video va M3U8
chcp 65001 >nul
cd /d "%~dp0"

echo ======================================================================
echo          SUBVIET - TRICH XUAT PHU DE TIENG VIET TU DONG
echo    [AI VietOCR Transformer + Interactive Bounding Box + Tesseract]
echo ======================================================================
echo.

REM 1. Xac dinh trinh thuc thi Python
set PYTHON_EXE=
python --version >nul 2>&1
if not errorlevel 1 set PYTHON_EXE=python

if "%PYTHON_EXE%"=="" (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set PYTHON_EXE=py -3
)

if "%PYTHON_EXE%"=="" (
    echo [LOI] Khong tim thay Python tren he thong!
    echo Vui long cai dat Python 3.10 tro len va tick Add python.exe to PATH.
    pause
    exit /b 1
)

for /f "delims=" %%i in ('%PYTHON_EXE% --version 2^>^&1') do echo [OK] %%i

REM 2. Bo sung duong dan Tesseract vao PATH
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" set "PATH=C:\Program Files\Tesseract-OCR;%PATH%"
if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" set "PATH=C:\Program Files (x86)\Tesseract-OCR;%PATH%"
if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" set "PATH=%LOCALAPPDATA%\Programs\Tesseract-OCR;%PATH%"
where tesseract >nul 2>&1
if not errorlevel 1 echo [OK] Tesseract OCR da san sang.

REM 3. Thiet lap moi truong UTF-8 va tessdata
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
set TESSDATA_PREFIX=%~dp0tessdata

REM 4. Kiem tra thu vien VietOCR
%PYTHON_EXE% -c "import vietocr" >nul 2>&1
if not errorlevel 1 echo [OK] AI VietOCR (Transformer) da san sang.
if errorlevel 1 goto install_vietocr
goto check_data

:install_vietocr
echo [!] Dang tu dong cai dat VietOCR...
%PYTHON_EXE% -m pip install vietocr --no-deps
%PYTHON_EXE% -m pip install einops lmdb gdown prefetch-generator

:check_data
if exist "%~dp0data\vietnamese_syllables.txt" echo [OK] Tu dien 8875 am tiet tieng Viet da san sang.
if exist "%~dp0tessdata\vie.traineddata" echo [OK] Tu dien Tesseract tieng Viet da san sang.
if not exist "%~dp0tessdata\vie.traineddata" echo [i] Tu dien Tesseract vie.traineddata chua co.

REM 5. Don dep cache
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" >nul 2>&1

REM 6. Khoi chay ung dung
echo.
echo [INFO] Dang khoi chay giao dien SubViet...
echo ======================================================================
%PYTHON_EXE% -X utf8 app.py

if errorlevel 1 (
    echo.
    echo ======================================================================
    echo [THONG BAO] Ung dung da dung hoac phat sinh loi.
    pause
)
