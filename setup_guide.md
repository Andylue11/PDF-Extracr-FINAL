# RFMS PDF XTRACR - Complete Setup Guide

## 🚀 Application Overview

The **RFMS PDF XTRACR** is a web-based application designed to streamline the extraction of data from uploaded PDF purchase orders (POs) and integrate it with the Retail Floor Management System (RFMS) using the RFMS API v2. This application features a single-screen dashboard that allows users to upload PDFs, extract key details, and perform actions such as creating quotes, jobs, or managing customers in RFMS.

## 📋 Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- Git (for version control)
- Access to RFMS API credentials

## 🔧 Installation & Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd RFMS-PDF-Xtracr-feature-new-fork
```

### 2. Create Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration

Create a `.env` file in the root directory with the following variables:

```env
# Flask Configuration
SECRET_KEY=your-secret-key-here
FLASK_DEBUG=True
PORT=5000

# Database Configuration
DATABASE_URL=sqlite:///rfms_xtracr.db

# Upload Configuration
UPLOAD_FOLDER=uploads
MAX_CONTENT_LENGTH=16777216  # 16MB

# RFMS API Configuration
RFMS_BASE_URL=https://api.rfms.online
RFMS_STORE_CODE=your-store-code
RFMS_USERNAME=your-username
RFMS_API_KEY=your-api-key
RFMS_STORE_NUMBER=49

# Email Configuration (Optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USERNAME=your-email@example.com
EMAIL_PASSWORD=your-app-password
```

### 5. Initialize Database
```bash
python init_db.py
```

### 6. Create Upload Directory
```bash
mkdir uploads
mkdir uploads_test
```

## 🏗️ Core Application Structure

### Main Application Files

#### `app.py` - Main Flask Application
- **Purpose**: Core Flask application with all routes and API endpoints
- **Key Features**:
  - PDF upload and processing
  - RFMS API integration
  - Customer management
  - Order/Quote creation
  - Dashboard with statistics

#### `utils/payload_service.py` - Payload Management
- **Purpose**: Handles RFMS API payload construction using the proven AZ002874 method
- **Key Functions**:
  - `build_rfms_customer_payload()` - Creates customer payloads
  - `build_rfms_order_payload()` - Creates order payloads with correct field mapping
  - `export_data_to_rfms()` - Main export function with billing group support

#### `utils/rfms_api.py` - RFMS API Client
- **Purpose**: Handles all RFMS API communications
- **Key Features**:
  - Session management
  - Customer search and creation
  - Order/Quote creation
  - Billing group management

#### `utils/pdf_extractor.py` - PDF Data Extraction
- **Purpose**: Extracts structured data from PDF purchase orders
- **Key Features**:
  - Multi-format PDF support
  - Builder-specific extraction patterns
  - Data validation and cleaning

### Database Models

#### `models/customer.py`
- `Customer` - Local customer records
- `ApprovedCustomer` - Cached approved customers from RFMS

#### `models/pdf_data.py`
- `PdfData` - Stores uploaded PDF metadata and extracted data

#### `models/job.py`
- `Job` - Job records with RFMS integration

#### `models/quote.py`
- `Quote` - Quote records with RFMS integration

#### `models/rfms_session.py`
- `RFMSSession` - RFMS API session management

## 🎯 Key Features & Workflows

### 1. PDF Upload & Data Extraction
```
User uploads PDF → PDF processed → Data extracted → Preview displayed
```

### 2. Customer Management
```
Search RFMS customers → Select/Create customer → Save to approved list
```

### 3. Order Creation (AZ002874 Method)
```
Extract data → Build payload → Create RFMS order → Handle billing groups
```

### 4. Dashboard Analytics
```
Track uploads → Monitor processing → Display statistics
```

## 🔄 API Endpoints

### Core Endpoints
- `POST /upload-pdf` - Upload and process PDF files
- `POST /api/export-to-rfms` - Export data to RFMS using AZ002874 method
- `POST /api/customers/search` - Search RFMS customers
- `POST /api/create_customer` - Create new RFMS customer
- `GET /api/check_status` - Check RFMS API connectivity

### Data Management
- `POST /api/approved_customer` - Save approved customer
- `GET /api/salesperson_values` - Get salesperson options
- `GET /api/get_default_salesperson` - Get default salesperson

## 🚀 Running the Application

### Development Mode
```bash
python app.py
```

### Production Mode
```bash
export FLASK_DEBUG=False
python app.py
```

The application will be available at `http://localhost:5000`

## 🧪 Testing

### Run Tests
```bash
pytest
```

### Test RFMS Connection
```bash
python -c "from utils.rfms_api import RfmsApi; print('RFMS API connection test')"
```

## 📁 Directory Structure

```
RFMS-PDF-Xtracr-feature-new-fork/
├── app.py                          # Main Flask application
├── requirements.txt                # Python dependencies
├── .env                           # Environment variables (create this)
├── mapping.md                     # Field mapping documentation
├── SETUP_GUIDE.md                 # This file
├── models/                        # Database models
│   ├── __init__.py
│   ├── customer.py
│   ├── job.py
│   ├── quote.py
│   ├── pdf_data.py
│   └── rfms_session.py
├── utils/                         # Utility modules
│   ├── __init__.py
│   ├── payload_service.py         # RFMS payload management
│   ├── rfms_api.py               # RFMS API client
│   ├── pdf_extractor.py          # PDF data extraction
│   └── email_utils.py            # Email utilities
├── templates/                     # HTML templates
├── static/                        # CSS, JS, images
├── uploads/                       # PDF upload directory
├── themes/                        # UI themes and logos
└── instance/                      # Instance-specific files
```

## 🔧 Configuration Details

### RFMS API Integration
The application uses the **AZ002874 method** for creating orders in RFMS:
- Flat payload structure (no nested 'order' wrapper)
- Proper field mapping as per `mapping.md`
- Support for billing groups with PO suffixes
- Comprehensive error handling

### PDF Processing
- Supports multiple PDF formats
- Builder-specific extraction patterns
- Automatic data validation
- Duplicate PO detection

### Database
- SQLite for development (configurable via DATABASE_URL)
- Automatic table creation
- Migration support through Flask-SQLAlchemy

## 🚨 Troubleshooting

### Common Issues

1. **RFMS API Connection Failed**
   - Check `.env` file for correct RFMS credentials
   - Verify network connectivity
   - Check RFMS API status

2. **PDF Extraction Errors**
   - Ensure PDF is not password-protected
   - Check file size (max 16MB)
   - Verify PDF format compatibility

3. **Database Errors**
   - Run `python init_db.py` to recreate tables
   - Check database file permissions
   - Verify SQLAlchemy configuration

### Logs
- Application logs are written to `app.log`
- Check console output for real-time debugging
- Enable debug mode for detailed error messages

## 📚 Additional Resources

- `mapping.md` - Complete field mapping documentation
- `RFMS PDF XTRACR Application Description and Methodology.markdown` - Detailed methodology
- RFMS API documentation in `rfms api docs/` folder
- UI layouts in `ui layouts/` folder

## 🎨 UI Customization

The application includes A to Z Flooring Solutions branding:
- Logo files in `themes/` directory
- Custom color schemes
- Responsive Tailwind CSS design
- Single-screen dashboard layout

## 🔒 Security Considerations

- Environment variables for sensitive data
- File upload restrictions (PDF only, 16MB max)
- Input validation and sanitization
- HTTPS recommended for production

## 📞 Support

For technical support or questions about the RFMS PDF XTRACR application, refer to the project documentation or contact the development team.

---

**Last Updated**: December 2024
**Version**: 2.0 (AZ002874 Method Implementation)
