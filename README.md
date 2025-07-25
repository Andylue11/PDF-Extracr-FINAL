# RFMS PDF XTRACR - Master Application

A Flask-based web application for extracting data from PDF quotes and creating orders in the RFMS system.

## Features

- **PDF Data Extraction**: Automatically extract customer, job, and quote information from PDF files
- **RFMS Integration**: Create orders directly in the RFMS system using the proven AZ002874 method
- **Web Interface**: User-friendly web interface for uploading PDFs and managing orders
- **Database Management**: SQLite database for storing extracted data and order history
- **Email Integration**: Send notifications and updates via email

## Quick Start

### Prerequisites

- Python 3.7 or higher
- Windows PowerShell (for setup scripts)

### Installation

1. **Navigate to the master_app directory**

2. **Run the automated setup:**
   ```bash
   # For Windows Command Prompt:
   setup.bat
   
   # For PowerShell:
   .\setup.ps1
   ```

3. **Configure environment variables:**
   - Copy `env_example.txt` to `.env`
   - Update `.env` with your RFMS API credentials and settings

4. **Start the application:**
   ```bash
   python app.py
   ```

5. **Access the application:**
   - Open your browser to `http://localhost:5000`

## Configuration

### Environment Variables (.env file)

```env
# RFMS API Configuration
RFMS_BASE_URL=https://your-rfms-instance.com
RFMS_USERNAME=your_username
RFMS_PASSWORD=your_password

# Application Settings
FLASK_ENV=development
SECRET_KEY=your_secret_key_here

# Database
DATABASE_URL=sqlite:///rfms_extractor.db
```

## Usage

1. **Upload PDF**: Navigate to the web interface and upload a PDF quote
2. **Review Data**: Check the extracted customer, job, and quote information
3. **Create Order**: Submit the order to RFMS using the integrated API
4. **Track Status**: Monitor order creation status and history

## Project Structure

```
master_app/
├── app.py                 # Main Flask application
├── init_db.py            # Database initialization
├── requirements.txt      # Python dependencies
├── setup.bat            # Windows batch setup script
├── setup.ps1            # PowerShell setup script
├── verify_setup.py      # Setup verification script
├── env_example.txt      # Environment variables template
├── models/              # Database models
│   ├── __init__.py
│   ├── customer.py
│   ├── job.py
│   ├── quote.py
│   ├── pdf_data.py
│   └── rfms_session.py
├── utils/               # Utility modules
│   ├── __init__.py
│   ├── pdf_extractor.py # PDF processing
│   ├── rfms_api.py      # RFMS API integration
│   ├── payload_service.py # Order payload creation
│   └── email_utils.py   # Email functionality
├── templates/           # HTML templates
│   ├── base.html
│   ├── index.html
│   └── preview.html
├── static/              # CSS, JS, images
│   ├── css/
│   ├── js/
│   └── themes/
├── uploads/             # PDF upload directory
└── uploads_test/        # Test upload directory
```

## API Integration

The application uses the proven **AZ002874 method** for creating orders in RFMS:

- **Endpoint**: `/v2/order/create`
- **Method**: POST
- **Authentication**: Basic Auth with RFMS credentials
- **Payload**: Structured JSON with customer, job, and line item data

See `AZ002874_PRODUCTION_METHOD.md` for detailed payload structure and field mappings.

## Documentation

- `QUICK_START.md` - Quick setup and usage guide
- `setup_guide.md` - Comprehensive setup instructions
- `mapping.md` - Field mapping documentation
- `AZ002874_PRODUCTION_METHOD.md` - Production method details

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure virtual environment is activated and dependencies are installed
2. **Database Errors**: Run `python init_db.py` to initialize the database
3. **API Connection**: Check RFMS credentials and network connectivity
4. **PDF Processing**: Ensure uploaded PDFs are readable and contain expected data

### Verification

Run the setup verification script to check your installation:

```bash
python verify_setup.py
```

## Support

For technical support:
1. Check the documentation files in this directory
2. Review the setup guide: `setup_guide.md`
3. Verify your setup with: `python verify_setup.py`

## License

This project is proprietary software for RFMS integration.
