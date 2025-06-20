@echo off
echo ========================================
echo RFMS PDF XTRACR - Automated Setup
echo ========================================
echo.

echo Step 1: Creating virtual environment...
py -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)
echo ✓ Virtual environment created

echo.
echo Step 2: Activating virtual environment...
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)
echo ✓ Virtual environment activated

echo.
echo Step 3: Upgrading pip...
python -m pip install --upgrade pip
if %errorlevel% neq 0 (
    echo ERROR: Failed to upgrade pip
    pause
    exit /b 1
)
echo ✓ Pip upgraded

echo.
echo Step 4: Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo ✓ Dependencies installed

echo.
echo Step 5: Creating upload directories...
if not exist "uploads" mkdir uploads
if not exist "uploads_test" mkdir uploads_test
echo ✓ Upload directories created

echo.
echo Step 6: Initializing database...
python init_db.py
if %errorlevel% neq 0 (
    echo ERROR: Failed to initialize database
    pause
    exit /b 1
)
echo ✓ Database initialized

echo.
echo ========================================
echo Setup completed successfully!
echo ========================================
echo.
echo Next steps:
echo 1. Copy env_example.txt to .env
echo 2. Update .env with your RFMS API credentials
echo 3. Run: python app.py
echo.
echo The application will be available at: http://localhost:5000
echo.
pause 