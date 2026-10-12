@echo off
title SubViet - Trich Xuat Anh Phu De (Subtitle Cropper)
chcp 65001 >nul
cd /d "%~dp0"

echo ======================================================================
echo       SUBVIET - TRICH XUAT ANH PHU DE THEO VUNG CHON (IMAGE CROPPER)
echo       Tu dong cat vung sub va danh so luu vao: anhsub\
echo ======================================================================
echo.

REM 1. Xac dinh Python
set PYTHON_EXE=
python --version >nul 2>&1
if not errorlevel 1 set PYTHON_EXE=python

if "%PYTHON_EXE%"=="" (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set PYTHON_EXE=py -3
)

if "%PYTHON_EXE%"=="" (
    echo [LOI] Khong tim thay Python tren he thong!
    pause
    exit /b 1
)

for /f "delims=" %%i in ('%PYTHON_EXE% --version 2^>^&1') do echo [OK] %%i

REM 2. Don dep cache
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" >nul 2>&1

REM 3. Khoi chay ung dung trich xuat anh
echo.
echo [INFO] Dang mo ung dung trich xuat anh phu de...
echo ======================================================================
%PYTHON_EXE% -X utf8 extract_sub_images.py

if errorlevel 1 (
    echo.
    echo [THONG BAO] Ung dung da dung hoac phat sinh loi.
    pause
)