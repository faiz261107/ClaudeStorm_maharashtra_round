@echo off
REM Re:Learn — Windows one-click start
cd /d "%~dp0"
if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python run.py
