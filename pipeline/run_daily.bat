@echo off
REM ═══════════════════════════════════════════════════════════════
REM  LinkedIn SDR Agent — Daily Pipeline Runner (Windows)
REM  Run via Windows Task Scheduler or manually
REM ═══════════════════════════════════════════════════════════════

SET PROJECT_DIR=%~dp0..
SET LOG_DIR=%PROJECT_DIR%\data\logs
SET LOG_FILE=%LOG_DIR%\pipeline_%date:~-4,4%%date:~-7,2%%date:~-10,2%.log

REM Create logs directory if it doesn't exist
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Activate virtual environment if it exists
if exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" (
    call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
) else if exist "%PROJECT_DIR%\venv\Scripts\activate.bat" (
    call "%PROJECT_DIR%\venv\Scripts\activate.bat"
)

REM Change to project directory
cd /d "%PROJECT_DIR%"

REM Load environment variables from .env if it exists
if exist "%PROJECT_DIR%\.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%PROJECT_DIR%\.env") do (
        REM Skip comments and empty lines
        echo %%a | findstr /r "^#" >nul || set "%%a=%%b"
    )
)

REM Run the pipeline
echo [%date% %time%] Starting daily pipeline... >> "%LOG_FILE%"
python -m pipeline.daily_run --min-score 70 >> "%LOG_FILE%" 2>&1
SET EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% EQU 0 (
    echo [%date% %time%] Pipeline completed successfully. >> "%LOG_FILE%"
) else (
    echo [%date% %time%] Pipeline failed with exit code %EXIT_CODE%. >> "%LOG_FILE%"
)

echo [%date% %time%] Done. >> "%LOG_FILE%"
