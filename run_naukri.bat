@echo off
REM Navigate to your local repo
cd /d "C:\Users\Amey\python\naukri"

REM Pull the latest code from GitHub
git pull

REM Run the Python script
python naukri_apply.py
