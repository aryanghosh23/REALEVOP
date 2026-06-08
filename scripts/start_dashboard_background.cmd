@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Python virtual environment was not found at .venv.
    echo Run: python -m venv .venv
    echo Then: .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

start "REALEVOP Dashboard" /min "%ComSpec%" /c "scripts\run_streamlit_logged.cmd"
echo Dashboard starting at http://127.0.0.1:8501
echo Runtime log: logs\streamlit-runtime.log
