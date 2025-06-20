from models import db
from datetime import datetime

class RFMSSession(db.Model):
    __tablename__ = 'rfms_session'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(256), nullable=False)
    expiry = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) 