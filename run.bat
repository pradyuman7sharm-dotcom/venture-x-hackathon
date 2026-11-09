@echo off
title Sahaayak Pro
cd /d "%~dp0"
echo Starting Sahaayak Pro on http://localhost:8080 ...
python app.py --port 8080
pause
