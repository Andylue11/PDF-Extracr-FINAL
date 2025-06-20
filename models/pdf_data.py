from models import db
from datetime import datetime
import json


class PdfData(db.Model):
    """
    Model for storing extracted data from PDF files.
    """

    id = db.Column(db.Integer, primary_key=True)

    # PDF file information
    filename = db.Column(db.String(255))
    file_path = db.Column(db.String(255), nullable=True)

    # Extracted key data
    customer_name = db.Column(db.String(100))
    business_name = db.Column(db.String(100))
    po_number = db.Column(db.String(50))
    scope_of_work = db.Column(db.Text)
    dollar_value = db.Column(db.Float, default=0.0)

    # Store all extracted fields as JSON
    extracted_data_json = db.Column(db.Text)

    # Status and tracking
    processed = db.Column(db.Boolean, default=False)
    quote_id = db.Column(db.Integer, db.ForeignKey("quote.id"), nullable=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<PdfData {self.filename} - PO:{self.po_number}>"

    @property
    def extracted_data(self):
        """
        Get the extracted data as a dictionary.
        """
        if self.extracted_data_json:
            return json.loads(self.extracted_data_json)
        return {}

    @extracted_data.setter
    def extracted_data(self, data):
        """
        Set the extracted data from a dictionary.
        """
        if data:
            self.extracted_data_json = json.dumps(data)

    def to_dict(self):
        """
        Convert the model instance to a dictionary.
        """
        return {
            "id": self.id,
            "filename": self.filename,
            "file_path": self.file_path,
            "customer_name": self.customer_name,
            "business_name": self.business_name,
            "po_number": self.po_number,
            "scope_of_work": self.scope_of_work,
            "dollar_value": self.dollar_value,
            "extracted_data": self.extracted_data,
            "processed": self.processed,
            "quote_id": self.quote_id,
            "job_id": self.job_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
