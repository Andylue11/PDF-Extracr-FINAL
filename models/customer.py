from models import db
from datetime import datetime


class Customer(db.Model):
    """
    Customer model for storing customer information.
    """

    id = db.Column(db.Integer, primary_key=True)

    # Basic customer information
    salutation = db.Column(db.String(10))
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    business_name = db.Column(db.String(100))
    address = db.Column(db.String(100))
    city = db.Column(db.String(50))
    state = db.Column(db.String(2))
    zip_code = db.Column(db.String(15))
    country = db.Column(db.String(50), default="USA")

    # Contact information
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))

    # RFMS specific fields
    rfms_customer_id = db.Column(db.String(50), nullable=True)
    custom_id = db.Column(db.String(50), nullable=True)
    customer_type = db.Column(db.String(50), default="INSURED CUSTOMER")
    active_date = db.Column(db.Date, default=datetime.now)
    renewal_date = db.Column(db.Date, nullable=True)
    renewal_amount = db.Column(db.Float, default=0.0)
    renewal_group = db.Column(db.String(50), nullable=True)
    default_store = db.Column(db.String(50), nullable=True)
    buyer_type = db.Column(db.String(50), nullable=True)
    sales_rep = db.Column(db.String(50), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    quotes = db.relationship("Quote", backref="customer", lazy=True)
    jobs = db.relationship("Job", backref="customer", lazy=True)

    def __repr__(self):
        return f"<Customer {self.first_name} {self.last_name} ({self.business_name})>"

    def to_dict(self):
        """
        Convert the model instance to a dictionary.
        """
        return {
            "id": self.id,
            "salutation": self.salutation,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "business_name": self.business_name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "country": self.country,
            "phone": self.phone,
            "email": self.email,
            "rfms_customer_id": self.rfms_customer_id,
            "custom_id": self.custom_id,
            "customer_type": self.customer_type,
            "active_date": (
                self.active_date.strftime("%Y-%m-%d") if self.active_date else None
            ),
            "renewal_date": (
                self.renewal_date.strftime("%Y-%m-%d") if self.renewal_date else None
            ),
            "renewal_amount": self.renewal_amount,
            "renewal_group": self.renewal_group,
            "default_store": self.default_store,
            "buyer_type": self.buyer_type,
            "sales_rep": self.sales_rep,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    def from_rfms_data(cls, rfms_data):
        """
        Create a Customer instance from RFMS API data.

        Args:
            rfms_data (dict): Customer data from RFMS API

        Returns:
            Customer: New Customer instance
        """
        customer = cls(
            salutation=rfms_data.get("salutation"),
            first_name=rfms_data.get("firstName"),
            last_name=rfms_data.get("lastName"),
            business_name=rfms_data.get("name"),
            address=rfms_data.get("address1"),
            city=rfms_data.get("city"),
            state=rfms_data.get("state"),
            zip_code=rfms_data.get("postalCode"),
            country=rfms_data.get("country", "USA"),
            phone=rfms_data.get("phone"),
            email=rfms_data.get("email"),
            rfms_customer_id=rfms_data.get("id"),
            custom_id=rfms_data.get("customId"),
            customer_type=rfms_data.get("type", "INSURED CUSTOMER"),
            active_date=datetime.strptime(
                rfms_data.get("activeDate", datetime.now().strftime("%Y-%m-%d")),
                "%Y-%m-%d",
            ),
            default_store=rfms_data.get("storeCode"),
        )

        if "renewalDate" in rfms_data and rfms_data["renewalDate"]:
            customer.renewal_date = datetime.strptime(
                rfms_data["renewalDate"], "%Y-%m-%d"
            )

        if "renewalAmount" in rfms_data:
            customer.renewal_amount = float(rfms_data["renewalAmount"])

        if "renewalGroup" in rfms_data:
            customer.renewal_group = rfms_data["renewalGroup"]

        if "buyerType" in rfms_data:
            customer.buyer_type = rfms_data["buyerType"]

        if "salesRep" in rfms_data:
            customer.sales_rep = rfms_data["salesRep"]

        return customer


class ApprovedCustomer(db.Model):
    """
    Stores approved/accepted 'sold to' customers for persistent caching.
    """
    __tablename__ = 'approved_customer'
    id = db.Column(db.Integer, primary_key=True)
    rfms_customer_id = db.Column(db.String(50), nullable=False, unique=True)
    name = db.Column(db.String(100))
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    business_name = db.Column(db.String(100))
    address = db.Column(db.String(100))
    city = db.Column(db.String(50))
    state = db.Column(db.String(2))
    zip_code = db.Column(db.String(15))
    country = db.Column(db.String(50), default="Australia")
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    approved_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<ApprovedCustomer {self.name} ({self.rfms_customer_id})>"

    def to_dict(self):
        return {
            "id": self.id,
            "rfms_customer_id": self.rfms_customer_id,
            "name": self.name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "business_name": self.business_name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "country": self.country,
            "phone": self.phone,
            "email": self.email,
            "approved_at": self.approved_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
