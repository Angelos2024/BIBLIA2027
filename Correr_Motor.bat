@echo off
chcp 65001 >nul
cd /d "%~dp0"
python motores\correr_motor.py %*
echo.
pause
