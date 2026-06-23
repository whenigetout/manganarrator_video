@echo off
setlocal
call conda activate manganarrator-video
python scripts\sync_contracts.py
uvicorn video_server:app --host 0.0.0.0 --port 8084 --reload
endlocal
