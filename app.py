# === WATCHER HEADER START ===
# File: app.py
# Managed by file watcher
# === WATCHER HEADER END ===
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    flash,
    redirect,
    url_for,
    session,
)
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import logging
from datetime import datetime
import tempfile
import json

# Load environment variables FIRST
load_dotenv(dotenv_path=".env")

# Import models and database
from models import db, Customer, Quote, Job, PdfData
from models.customer import ApprovedCustomer

# Import utility modules
from utils.pdf_extractor import extract_data_from_pdf
from utils.rfms_api import RfmsApi
from utils.email_utils import EmailSender
# Import the payload service with comprehensive format support
from utils import payload_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)

# App configuration
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
# Ensure DATABASE_URI is used, allowing different DBs for different forks via .env
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///rfms_xtracr.db" # Changed from DATABASE_URI to DATABASE_URL for clarity or stick to DATABASE_URI if preferred
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload size
app.config["ALLOWED_EXTENSIONS"] = {"pdf"}

# Disable caching in development
@app.after_request
def add_header(response):
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

# Ensure upload directory exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Initialize database with app
db.init_app(app)

# RFMS API Client Initialization
rfms_base_url = os.getenv("RFMS_BASE_URL", "https://api.rfms.online")
rfms_store_code = os.getenv("RFMS_STORE_CODE")
rfms_username = os.getenv("RFMS_USERNAME")
rfms_api_key = os.getenv("RFMS_API_KEY")

logger.info(f"RFMS PDF Xtracr - Comprehensive Format Enabled")
logger.info(f"Using AZ002876 successful structure + comprehensive lines")
logger.info(f"RFMS API Configuration:")
logger.info(f"  Base URL: {rfms_base_url}")
logger.info(f"  Store Code: {'Loaded' if rfms_store_code else 'Missing'}")
logger.info(f"  Username: {'Loaded' if rfms_username else 'Missing'}")
logger.info(f"  API Key: {'Loaded' if rfms_api_key else 'Missing'}")

missing_credentials = []
if not rfms_store_code:
    missing_credentials.append("RFMS_STORE_CODE")
if not rfms_username:
    missing_credentials.append("RFMS_USERNAME")
if not rfms_api_key:
    missing_credentials.append("RFMS_API_KEY")

rfms_api_client = None
if missing_credentials:
    logger.error(f"Missing required RFMS API credentials: {', '.join(missing_credentials)}")
    logger.error("Please check your .env file and ensure all RFMS_* variables are set. RFMS API client will not be functional.")
else:
    rfms_api_client = RfmsApi(
        base_url=rfms_base_url,
        store_code=rfms_store_code,
        username=rfms_username,
        api_key=rfms_api_key,
    )
    logger.info("RFMS API client initialized successfully with comprehensive format support")

def ensure_rfms_api():
    if rfms_api_client is None:
        raise Exception("RFMS API client not configured or failed to initialize. Please check credentials and logs.")
    # Optional: Add a ping or status check here if the client supports it
    # rfms_api_client.ensure_session() # Assuming this is still needed and part of your RfmsApi class
    return rfms_api_client

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )

# PDF Extractor is now function-based, no initialization needed

@app.route("/")
def index():
    recent_pdfs = PdfData.query.order_by(PdfData.created_at.desc()).limit(5).all()
    total_uploads = PdfData.query.count()
    processed_uploads = PdfData.query.filter_by(processed=True).count()
    quotes_created = Quote.query.count()
    jobs_created = Job.query.count()
    stats = {
        "total_uploads": total_uploads,
        "processed_uploads": processed_uploads,
        "quotes_created": quotes_created,
        "jobs_created": jobs_created,
    }
    return render_template("index.html", recent_pdfs=recent_pdfs, stats=stats)

@app.route("/upload-pdf", methods=["POST"])
def upload_pdf_api():
    api_client = ensure_rfms_api()
    session_ok = api_client.ensure_session() # Assuming ensure_session is part of your RfmsApi class
    logger.info(
        f"RFMS session ready after PDF upload: {session_ok}, token: {api_client.session_token}, expiry: {api_client.session_expiry}"
    )
    if not session_ok:
        return jsonify({"error": "Could not establish RFMS session. Please try again."}), 500

    if "pdf_file" not in request.files:
        logger.warning("No file part in upload request.")
        return jsonify({"error": "No file part"}), 400

    file = request.files["pdf_file"]
    if file.filename == "":
        logger.warning("No selected file in upload request.")
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        builder_name = request.form.get('builder_name', '')
        logger.info(f"Processing PDF for builder: {builder_name}")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            file.save(tmp_file.name)
            temp_path = tmp_file.name
        try:
            extracted_data = extract_data_from_pdf(temp_path, builder_name=builder_name)
            logger.info(f"Successfully extracted data for {filename}")
            os.remove(temp_path)

            # --- Check for duplicate PO number in RFMS ---
            po_number = extracted_data.get("po_number", "")
            po_status = "unknown"
            po_message = ""
            if po_number:
                try:
                    result = api_client.find_order_by_po_number(po_number)
                    if result and isinstance(result, list) and len(result) > 0:
                        po_status = "duplicate"
                        po_message = "This purchase order already exists in RFMS. Please check before proceeding."
                    else:
                        po_status = "new"
                        po_message = "New purchase order approved for processing."
                except Exception as e:
                    logger.error(f"Error checking PO number in RFMS: {str(e)}")
                    po_status = "error"
                    po_message = f"Error checking PO number in RFMS: {str(e)}"
            else:
                po_status = "missing"
                po_message = "No purchase order number extracted from PDF."

            # Add PO status info to response
            extracted_data["po_status"] = po_status
            extracted_data["po_status_message"] = po_message

            # Enhanced UI mapping for phone fields and BEST CONTACT
            logger.info(f"[UI_MAPPING] Starting UI field mapping...")
            logger.info(f"[UI_MAPPING] Available data - pdf_phone3: '{extracted_data.get('pdf_phone3', '')}', pdf_phone4: '{extracted_data.get('pdf_phone4', '')}', alternate_contacts: {len(extracted_data.get('alternate_contacts', []))}")
            
            # Map PDF extracted phones to UI fields for display and editing
            if extracted_data.get("pdf_phone3") and not extracted_data.get("phone3"):
                extracted_data["phone3"] = extracted_data["pdf_phone3"]
                logger.info(f"[UI_MAPPING] Mapped pdf_phone3 '{extracted_data['pdf_phone3']}' to phone3 field for UI display")
            
            if extracted_data.get("pdf_phone4") and not extracted_data.get("phone4"):
                extracted_data["phone4"] = extracted_data["pdf_phone4"]
                logger.info(f"[UI_MAPPING] Mapped pdf_phone4 '{extracted_data['pdf_phone4']}' to phone4 field for UI display")
            
            # Build consolidated BEST CONTACT field from alternate_contacts
            alt_contacts = extracted_data.get("alternate_contacts", [])
            if alt_contacts:
                best_contact_lines = []
                available_phones = []
                
                # Build contact summary text and collect all phones
                for contact in alt_contacts:
                    if contact.get("name") and contact.get("name").strip():
                        contact_line = f"{contact.get('type', 'Contact')}: {contact.get('name')}"
                        if contact.get("phone"):
                            contact_line += f" ({contact.get('phone')})"
                            if contact.get("phone") not in available_phones:
                                available_phones.append(contact.get("phone"))
                        if contact.get("phone2"):
                            contact_line += f", {contact.get('phone2')}"
                            if contact.get("phone2") not in available_phones:
                                available_phones.append(contact.get("phone2"))
                        if contact.get("email"):
                            contact_line += f" - {contact.get('email')}"
                        best_contact_lines.append(contact_line)
                
                # Set BEST CONTACT field
                if best_contact_lines:
                    extracted_data["best_contact_summary"] = "; ".join(best_contact_lines)
                    logger.info(f"[UI_MAPPING] Created best_contact_summary: '{extracted_data['best_contact_summary'][:100]}...'")
                
                # Ensure phone3 and phone4 are set from available phones if not already set
                if not extracted_data.get("phone3") and available_phones:
                    extracted_data["phone3"] = available_phones[0]
                    logger.info(f"[UI_MAPPING] Set phone3 from alternate_contacts: '{available_phones[0]}'")
                
                if not extracted_data.get("phone4") and len(available_phones) > 1:
                    extracted_data["phone4"] = available_phones[1] 
                    logger.info(f"[UI_MAPPING] Set phone4 from alternate_contacts: '{available_phones[1]}'")
            
            logger.info(f"[UI_MAPPING] Final UI fields - phone3: '{extracted_data.get('phone3', '')}', phone4: '{extracted_data.get('phone4', '')}', best_contact_summary: '{extracted_data.get('best_contact_summary', '')[:50]}...'")

            return jsonify(extracted_data), 200
        except Exception as e:
            logger.error(f"Error extracting data from PDF {filename}: {str(e)}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify({"error": f"Error extracting data: {str(e)}"}), 500
    else:
        logger.warning(f"Invalid file type uploaded: {file.filename}")
        return jsonify({"error": "Invalid file type. Please upload a PDF."}), 400

@app.route("/upload", methods=["POST"])
def upload_file():
    """Handles PDF upload, extraction, saves to DB, and redirects to preview."""
    if "pdf_file" not in request.files:
        flash("No file part")
        return redirect(request.url)

    file = request.files["pdf_file"]
    if file.filename == "":
        flash("No selected file")
        return redirect(request.url)

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # It's often better to save to a temporary location first,
        # or process in memory if possible, rather than directly to UPLOAD_FOLDER
        # before validation and extraction are complete.
        # For now, keeping original logic but consider changing if uploads are large/frequent.
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

        try:
            extracted_data = extract_data_from_pdf(file_path, builder_name="")
            
            # --- Check for duplicate PO number in RFMS ---
            api_client = ensure_rfms_api()
            po_number = extracted_data.get("po_number", "")
            po_status = "unknown"
            po_message = ""
            if po_number:
                try:
                    result = api_client.find_order_by_po_number(po_number)
                    if result and isinstance(result, list) and len(result) > 0:
                        po_status = "duplicate"
                        po_message = "This purchase order already exists in RFMS. Please check before proceeding."
                    else:
                        po_status = "new"
                        po_message = "New purchase order approved for processing."
                except Exception as e:
                    logger.error(f"Error checking PO number in RFMS: {str(e)}")
                    po_status = "error"
                    po_message = f"Error checking PO number in RFMS: {str(e)}"
            else:
                po_status = "missing"
                po_message = "No purchase order number extracted from PDF."

            # Add PO status info to response and DB
            extracted_data["po_status"] = po_status
            extracted_data["po_status_message"] = po_message

            # Map PDF extracted phones to UI fields for display and editing
            # This ensures the alternate contact phones appear in the Phone 3 and Phone 4 fields
            if extracted_data.get("pdf_phone3") and not extracted_data.get("phone3"):
                extracted_data["phone3"] = extracted_data["pdf_phone3"]
                logger.info(f"[UI_MAPPING] Mapped pdf_phone3 '{extracted_data['pdf_phone3']}' to phone3 field for UI display")
            
            if extracted_data.get("pdf_phone4") and not extracted_data.get("phone4"):
                extracted_data["phone4"] = extracted_data["pdf_phone4"]
                logger.info(f"[UI_MAPPING] Mapped pdf_phone4 '{extracted_data['pdf_phone4']}' to phone4 field for UI display")

            pdf_data_entry = PdfData(
                filename=filename,
                customer_name=extracted_data.get("customer_name", ""),
                business_name=extracted_data.get("business_name", ""),
                po_number=extracted_data.get("po_number", ""),
                scope_of_work=extracted_data.get("scope_of_work", ""),
                dollar_value=extracted_data.get("dollar_value", 0),
                extracted_data=extracted_data, # Storing the full JSON
                created_at=datetime.now(),
                # processed=False # Initialize as not processed until user confirms
            )
            db.session.add(pdf_data_entry)
            db.session.commit()

            flash(f"File '{filename}' uploaded and data extracted. Please review below.")
            return redirect(url_for("preview_data", pdf_id=pdf_data_entry.id))

        except Exception as e:
            logger.error(f"Error processing uploaded PDF {filename}: {str(e)}")
            flash(f"Error processing PDF: {str(e)}")
            # Optionally remove the saved file if processing failed
            if os.path.exists(file_path):
                 os.remove(file_path)
            return redirect(request.url)
    else:
        flash("Invalid file type. Please upload a PDF.")
    return redirect(request.url)


@app.route("/preview/<int:pdf_id>")
def preview_data(pdf_id):
    pdf_data = PdfData.query.get_or_404(pdf_id)
    # Extracted data is now in pdf_data.extracted_data
    return render_template("preview.html", pdf_data=pdf_data, extracted_data_json=json.dumps(pdf_data.extracted_data))


@app.route("/api/customers/search", methods=["POST"])
def search_customers():
    api_client = ensure_rfms_api()
    data = request.get_json()
    search_term = data.get("term", "") if data else ""
    start_index = int(data.get("start_index", 0)) if data else 0

    if not search_term:
        logger.warning("Empty search term provided")
        return jsonify({"error": "Search term is required."}), 400

    try:
        logger.info(f"Searching for customers with term: {search_term}, start_index: {start_index}")
        approved_matches = ApprovedCustomer.query.filter(
            (ApprovedCustomer.name.ilike(f"%{search_term}%")) |
            (ApprovedCustomer.business_name.ilike(f"%{search_term}%")) |
            (ApprovedCustomer.first_name.ilike(f"%{search_term}%")) |
            (ApprovedCustomer.last_name.ilike(f"%{search_term}%"))
        ).all()
        if approved_matches:
            logger.info(f"[APPROVED_CUSTOMER] Cache hit for search '{search_term}'")
            return jsonify([a.to_dict() for a in approved_matches])

        if search_term.isdigit():
            formatted_customers = api_client.find_customer_by_id(search_term)
        else:
            customers = api_client.find_customer_by_name(search_term, include_inactive=True, start_index=start_index)
            formatted_customers = api_client._format_customer_list(customers) # Assuming _format_customer_list is part of RfmsApi

        if not isinstance(formatted_customers, list) or not formatted_customers:
            logger.info(f"No customers found for search term: {search_term}")
            return jsonify([])
        
        logger.info(f"Found {len(formatted_customers)} customers for search term: {search_term}")
        return jsonify(formatted_customers)
    except Exception as e:
        logger.error(f"Error searching customers: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/create_customer", methods=["POST"])
def create_customer_api():
    api_client = ensure_rfms_api()
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    try:
        # Delegate payload building to the service
        customer_payload = payload_service.build_rfms_customer_payload(data)
        logger.info(f"[CREATE_CUSTOMER] Outgoing payload: {json.dumps(customer_payload, indent=2)}")
        result = api_client.create_customer(customer_payload)
        logger.info(f"[CREATE_CUSTOMER] RFMS API Response: {json.dumps(result, indent=2)}")
        # Potentially save/update to local ApprovedCustomer table here if successful
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error creating customer: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/create_quote", methods=["POST"])
def create_quote_api():
    api_client = ensure_rfms_api()
    quote_data = request.json # This is the payload expected by RFMS API's create_quote
    customer_id = quote_data.get('customer_id') # Or however customer_id is structured in your quote_data
    
    logger.info(f"[CREATE_QUOTE] Using customer ID: {customer_id}")
    if not customer_id: # Or more specific validation of quote_data
        logger.error("[CREATE_QUOTE] Missing customer_id in quote_data")
        return jsonify({"error": "Missing or invalid quote data."}), 400
    try:
        # If quote_data needs complex construction, move that to payload_service as well
        result = api_client.create_quote(quote_data)
        # Persist Quote to local DB
        # new_quote = Quote(...)
        # db.session.add(new_quote)
        # db.session.commit()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error creating quote: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/create_job", methods=["POST"])
def create_job_api():
    # This endpoint seems to be a direct passthrough for creating a single job.
    # The more complex "/api/export-to-rfms" handles the main UI-driven export.
    # If this is still needed, ensure its payload is correctly formed.
    api_client = ensure_rfms_api()
    job_data_payload = request.json # This is the raw payload for RFMS create_job

    customer_id = job_data_payload.get('order', {}).get('CustomerSeqNum')
    logger.info(f"[CREATE_JOB_DIRECT] Using customer ID: {customer_id}")
    if not customer_id:
        logger.error("[CREATE_JOB_DIRECT] Missing customer ID in job_data_payload['order']")
        return jsonify({"error": "Missing customer ID in job data."}), 400
    
    try:
        result = api_client.create_job(job_data_payload) # Pass the full payload
        # Persist Job to local DB
        # new_job = Job(...)
        # db.session.add(new_job)
        # db.session.commit()
        # Billing group logic was here before, decide if it belongs here or solely in export_to_rfms
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error creating job directly: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/export-to-rfms", methods=["POST"])
def export_to_rfms_api():
    """Export customer, job, and order data to RFMS API using comprehensive format."""
    api_client = ensure_rfms_api()
    export_request_data = request.json
    if not export_request_data:
        logger.warning("No data provided for RFMS export")
        return jsonify({"error": "No data provided for export"}), 400
    
    # Log the format transition
    logger.info("RFMS Export - Using Comprehensive Format (AZ002876 + Lines)")
    logger.info("Format Features: Customer fields + Phone optimization + Comprehensive lines")
    
    # Validate Description of Works (publicNotes) 5-word minimum
    description = ''
    if 'job_details' in export_request_data:
        description = export_request_data['job_details'].get('description_of_works', '')
    elif 'publicNotes' in export_request_data:
        description = export_request_data.get('publicNotes', '')
    word_count = len(description.strip().split())
    if word_count < 5:
        return jsonify({'error': 'General Scope of Works required!  example: Restrectch carpet back in bedroom two or Floor preperation PO for adding to billing group'}), 400

    # Basic validation (can be expanded in payload_service)
    required_sections = ["sold_to", "ship_to", "job_details"]
    for section in required_sections:
        if section not in export_request_data:
            logger.warning(f"Missing required section for export: {section}")
            return jsonify({"error": f"Missing required section: {section}"}), 400
            
    logger.info("Starting comprehensive format export to RFMS via /api/export-to-rfms")
    
    # Log key data for tracking
    sold_to_id = export_request_data.get("sold_to", {}).get("id") or export_request_data.get("sold_to", {}).get("customer_source_id")
    po_number = export_request_data.get("job_details", {}).get("po_number", "N/A")
    supervisor_name = export_request_data.get("job_details", {}).get("supervisor_name", "N/A")
    
    logger.info(f"Export Details: Customer ID={sold_to_id}, PO={po_number}, Supervisor={supervisor_name}")
    
    try:
        # Delegate payload construction and actual export logic to the service
        result = payload_service.export_data_to_rfms(api_client, export_request_data, logger)
        
        # Log success with format information
        order_id = result.get("order_id")
        format_used = result.get("format_used", "comprehensive_lines_az002876_structure")
        logger.info(f"RFMS Export Success: Order {order_id} created using {format_used}")
        
        # Update PdfData entry to processed = True if applicable
        pdf_id = export_request_data.get("pdf_id") # Assuming you pass this from frontend
        if pdf_id:
            pdf_entry = PdfData.query.get(pdf_id)
            if pdf_entry:
                pdf_entry.processed = True
                # Store RFMS job/quote IDs if available in result (column not yet added to model)
                # pdf_entry.rfms_job_id = result.get("order_id") 
                db.session.commit()
                logger.info(f"Updated PDF entry {pdf_id} as processed")

        return jsonify(result)
    except payload_service.PayloadError as pe: # Custom exception from service for bad data
        logger.error(f"Payload construction error during RFMS export: {str(pe)}")
        return jsonify({"error": f"Data validation error: {str(pe)}"}), 400
    except Exception as e:
        logger.error(f"Error during comprehensive format RFMS export: {str(e)}")
        # Consider more specific error handling based on exceptions from RfmsApi
        return jsonify({"error": f"An unexpected error occurred during RFMS export: {str(e)}"}), 500


@app.route("/api/check_status")
def check_api_status():
    try:
        api_client = ensure_rfms_api()
        status = api_client.check_status() # Assuming check_status exists in RfmsApi
        return jsonify({"status": status})
    except Exception as e:
        logger.error(f"API status check failed: {str(e)}")
        return jsonify({"status": "offline", "error": str(e)}), 500

@app.route("/api/salesperson_values")
def get_salesperson_values():
    api_client = ensure_rfms_api()
    try:
        # This logic to derive salespersons is a workaround. 
        # If RFMS API has a direct endpoint, use that.
        customers = api_client.find_customer_by_name("", include_inactive=False, start_index=0)
        salesperson_values = set()
        if isinstance(customers, list):
            for customer in customers:
                if isinstance(customer, dict):
                    for key in ["preferredSalesperson1", "preferredSalesperson2", "SalesPerson1", "SalesPerson2"]: # Broader check
                        sp = customer.get(key, "").strip()
                        if sp: salesperson_values.add(sp)
        
        salesperson_values.add("ZORAN VEKIC") # Default/fallback
        return jsonify(sorted(list(salesperson_values)))
    except Exception as e:
        logger.error(f"Error getting salesperson values: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/get_default_salesperson")
def get_default_salesperson():
    # This can be expanded to fetch from a config or a dedicated RFMS endpoint if available
    default_salesperson = "ZORAN VEKIC" 
    try:
        # For now, just return the default and optionally all values
        # To avoid redundant API call, consider if /api/salesperson_values is sufficient
        # and the frontend can determine the default.
        return jsonify({
            "default": default_salesperson,
            "values": [default_salesperson] # Or call logic similar to get_salesperson_values if needed here too
        })
    except Exception as e:
        logger.error(f"Error getting default salesperson: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/clear_data", methods=["POST"]) # Should probably be GET if just clearing session for redirect
def clear_data():
    # session.pop("extracted_data", None) # If you were using this for preview
    # This route might not be needed if preview data is fetched by pdf_id
    flash("Form cleared for next upload.")
    return redirect(url_for("index"))

@app.route("/api/approved_customer", methods=["POST"])
def save_approved_customer():
    data = request.json
    rfms_customer_id = data.get("customer_source_id") or data.get("id")
    if not rfms_customer_id:
        return jsonify({"error": "Missing customer_source_id or id"}), 400

    approved = ApprovedCustomer.query.filter_by(rfms_customer_id=str(rfms_customer_id)).first()
    
    customer_details = {
        "name": data.get("name"),
        "first_name": data.get("first_name"),
        "last_name": data.get("last_name"),
        "business_name": data.get("business_name"),
        "address": data.get("address1"), # Assuming address1 is primary
        "city": data.get("city"),
        "state": data.get("state"),
        "zip_code": data.get("zip_code"),
        "country": data.get("country"),
        "phone": data.get("phone"),
        "email": data.get("email"),
    }

    if approved: # Update existing
        for key, value in customer_details.items():
            if value is not None: # Only update if provided
                setattr(approved, key, value)
        status_msg = "updated"
    else: # Create new
        approved = ApprovedCustomer(rfms_customer_id=str(rfms_customer_id), **customer_details)
        db.session.add(approved)
        status_msg = "saved"
    
    try:
        db.session.commit()
        logger.info(f"[APPROVED_CUSTOMER] {status_msg.capitalize()}: RFMS ID {rfms_customer_id}")
        return jsonify({"status": status_msg, "customer": approved.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving approved customer: {str(e)}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    debug_mode = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "t")
    port = int(os.getenv("PORT", 5000))
    logger.info(f"Starting application in {'debug' if debug_mode else 'production'} mode on port {port}")
    app.run(debug=debug_mode, host="0.0.0.0", port=port)
