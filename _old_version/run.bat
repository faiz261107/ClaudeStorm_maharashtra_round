@echo off
pip install -r requirements.txt
start http://localhost:8000
uvicorn app:app --reload
