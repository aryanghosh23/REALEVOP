@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" (
    echo Python virtual environment was not found at .venv.
    echo Run: python -m venv .venv
    echo Then: .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

start "REALEVOP Dashboard" /b ".venv\Scripts\pythonw.exe" -m streamlit run dashboard/app.py --server.headless true --server.port 8501
echo Dashboard starting at http://127.0.0.1:8501

