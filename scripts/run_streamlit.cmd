@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\streamlit.exe" (
    echo Streamlit was not found in .venv.
    echo Run: .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

echo Starting EV Charging Energy Optimization dashboard...
echo Local URL: http://localhost:8501
echo Press Ctrl+C to stop the dashboard.
".venv\Scripts\streamlit.exe" run dashboard/app.py --server.headless true --server.port 8501
