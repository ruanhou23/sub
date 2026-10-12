@echo off
title SubViet - Nhan Dien Anh Xuat File SRT
chcp 65001 >nul
cd /d "%~dp0"

echo ======================================================================
echo    SUBVIET - NHAN DIEN ANH PHU DE XUAT FILE SRT (IMAGE-TO-SRT)
echo    [AI VietOCR Transformer + Smart Timestamp + Table Editor]
echo ======================================================================
echo.

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

for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" >nul 2>&1

echo.
echo [INFO] Dang mo ung dung nhan dien anh sang SRT...
echo ======================================================================
%PYTHON_EXE% -X utf8 app.py

if errorlevel 1 (
    echo.
    echo [THONG BAO] Ung dung da dung hoac phat sinh loi.
    pause
)