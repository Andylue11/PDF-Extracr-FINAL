# Quick Start Guide

# Upgrade pip
python -m pip install --upgrade pip

# Install all required packages
pip install -r requirements.txt

# Navigate to project directory
cd C:\Dev\RFMS-PDF-Xtracr-feature-new-fork

# Create virtual environment

py -m venv venv
# Activate virtual environment
.\venv\Scripts\activate.bat

# Flask Configuration
SECRET_KEY=your-secret-key-here
FLASK_DEBUG=True
PORT=5000

# Database Configuration
DATABASE_URL=sqlite:///rfms_xtracr.db

# RFMS API Configuration (REQUIRED)
RFMS_BASE_URL=https://api.rfms.online
RFMS_STORE_CODE=store-5291f4e3dca04334afede9f642ec6157
RFMS_USERNAME=store-5291f4e3dca04334afede9f642ec6157
RFMS_API_KEY=49bf22ea017f4b97aabc99def43c0b66
RFMS_STORE_NUMBER=49
