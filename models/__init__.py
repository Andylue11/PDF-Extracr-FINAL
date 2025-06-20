# Models package initialization
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Import models to make them available when importing the models package
# These imports are at the bottom to avoid circular import issues
from models.customer import Customer, ApprovedCustomer
from models.quote import Quote
from models.job import Job
from models.pdf_data import PdfData
from models.rfms_session import RFMSSession
