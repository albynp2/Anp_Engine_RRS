@echo off
setlocal
cd /d "%~dp0"
title Horror Content Factory - Local Launcher
if not exist ".env" (
  echo [ERROR] File .env belum ada. Copy .env.example menjadi .env lalu isi OPENAI_API_KEY.
  pause
  exit /b 1
)
if not exist "backend\node_modules" (
  echo [SETUP] Installing Node backend dependencies...
  pushd backend
  call npm install
  if errorlevel 1 (popd & echo Backend npm install gagal. Pastikan Node.js LTS terpasang. & pause & exit /b 1)
  popd
)
if not exist "frontend\node_modules" (
  echo [SETUP] Installing React frontend dependencies...
  pushd frontend
  call npm install
  if errorlevel 1 (popd & echo Frontend npm install gagal. Pastikan Node.js LTS terpasang. & pause & exit /b 1)
  popd
)
if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] Creating Python virtual environment...
  py -3.11 -m venv .venv 2>nul
  if errorlevel 1 python -m venv .venv
  if errorlevel 1 (echo Gagal membuat virtual environment. Install Python 3.11+ dan aktifkan Add Python to PATH.& pause & exit /b 1)
)
echo [SETUP] Installing/updating Python requirements...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Instalasi Python dependency gagal.& pause & exit /b 1)
set PYTHON_EXECUTABLE=%CD%\.venv\Scripts\python.exe
start "HCF Node API" cmd /k "cd /d ""%CD%\backend"" && set ""PYTHON_EXECUTABLE=%PYTHON_EXECUTABLE%"" && npm start"
start "HCF React UI" cmd /k "cd /d ""%CD%\frontend"" && npm run dev"
timeout /t 4 /nobreak >nul
start "" http://127.0.0.1:5173
echo.
echo Horror Content Factory is starting.
echo UI  : http://127.0.0.1:5173
echo API : http://127.0.0.1:3001/api/health
echo Do not close the two server windows while using the application.
echo.
pause
