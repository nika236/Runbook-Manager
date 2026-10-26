@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0Install.ps1"
pause
