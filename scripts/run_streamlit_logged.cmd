@echo off
setlocal
cd /d "%~dp0.."
if not exist logs mkdir logs
echo Starting dashboard at %DATE% %TIME% > logs\streamlit-runtime.log
".venv\Scripts\python.exe" -m streamlit run dashboard/app.py --server.headless true --server.port 8501 >> logs\streamlit-runtime.log 2>&1
echo Streamlit exited at %DATE% %TIME% with code %ERRORLEVEL% >> logs\streamlit-runtime.log

