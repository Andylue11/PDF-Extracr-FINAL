from models import db
from datetime import datetime


class Job(db.Model):
    """
    Job model for storing job information from RFMS.
    """

    id = db.Column(db.Integer, primary_key=True)

    # Basic job information
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    po_number = db.Column(db.String(50))
    scope_of_work = db.Column(db.Text)
    dollar_value = db.Column(db.Float, default=0.0)

    # RFMS specific fields
    rfms_job_id = db.Column(db.String(50), nullable=True)
    store_code = db.Column(db.String(50))
    job_type = db.Column(db.String(50), default="PO")

    # Billing group information
    is_billing_group = db.Column(db.Boolean, default=False)
    billing_group_id = db.Column(db.String(50), nullable=True)
    po_prefix = db.Column(db.String(50), nullable=True)
    po_suffix = db.Column(db.String(10), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Status tracking
    status = db.Column(db.String(20), default="CREATED")

    def __repr__(self):
        return f"<Job #{self.id} PO:{self.po_number} ${self.dollar_value}>"

    def to_dict(self):
        """
        Convert the model instance to a dictionary.
        """
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "po_number": self.po_number,
            "scope_of_work": self.scope_of_work,
            "dollar_value": self.dollar_value,
            "rfms_job_id": self.rfms_job_id,
            "store_code": self.store_code,
            "job_type": self.job_type,
            "is_billing_group": self.is_billing_group,
            "billing_group_id": self.billing_group_id,
            "po_prefix": self.po_prefix,
            "po_suffix": self.po_suffix,
            "status": self.status,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    def from_rfms_data(
        cls,
        rfms_data,
        customer_id,
        is_billing_group=False,
        po_prefix=None,
        po_suffix=None,
    ):
        """
        Create a Job instance from RFMS API data.

        Args:
            rfms_data (dict): Job data from RFMS API
            customer_id (int): Local customer ID
            is_billing_group (bool): Whether this job is part of a billing group
            po_prefix (str): PO prefix for billing group
            po_suffix (str): PO suffix for billing group

        Returns:
            Job: New Job instance
        """
        # Extract total dollar value from lines if available
        dollar_value = 0.0
        if "lines" in rfms_data:
            for line in rfms_data.get("lines", []):
                price = float(line.get("price", 0))
                quantity = float(line.get("quantity", 1))
                dollar_value += price * quantity

        job = cls(
            customer_id=customer_id,
            po_number=rfms_data.get("poNumber", ""),
            scope_of_work=rfms_data.get("workOrderNotes", ""),
            dollar_value=dollar_value,
            rfms_job_id=rfms_data.get("id"),
            store_code=rfms_data.get("storeCode", "1"),
            job_type=rfms_data.get("orderType", "PO"),
            status=rfms_data.get("status", "CREATED"),
            is_billing_group=is_billing_group,
            po_prefix=po_prefix,
            po_suffix=po_suffix,
        )

        if "billingGroupId" in rfms_data:
            job.billing_group_id = rfms_data["billingGroupId"]

        return job

    def to_rfms_data(self):
        """Convert job to RFMS API format according to exact payload structure."""
        return {
            "username": "zoran.vekic",
            "order": {
                "useDocumentWebOrderFlag": False,
                "originalMessageId": None,
                "newInvoiceNumber": None,
                "originalInvoiceNumber": None,
                "SeqNum": 0,
                "InvoiceNumber": "",
                "OriginalQuoteNum": "",
                "ActionFlag": "Insert",
                "InvoiceType": None,
                "IsQuote": False,
                "IsWebOrder": True,
                "Exported": False,
                "CanEdit": False,
                "LockTaxes": False,
                "CustomerSource": "Customer",
                "CustomerSeqNum": self.customer_id,
                "CustomerUpSeqNum": 0,
                "CustomerFirstName": "",
                "CustomerLastName": "",
                "CustomerAddress1": "",
                "CustomerAddress2": "",
                "CustomerCity": "",
                "CustomerState": "",
                "CustomerPostalCode": "",
                "CustomerCounty": "",
                "Phone1": "",
                "ShipToFirstName": "",
                "ShipToLastName": "",
                "ShipToAddress1": "",
                "ShipToAddress2": "",
                "ShipToCity": "",
                "ShipToState": "",
                "ShipToPostalCode": "",
                "Phone2": "",
                "Phone3": "",
                "ShipToLocked": False,
                "SalesPerson1": "ZORAN VEKIC",
                "SalesPerson2": "",
                "SalesRepLocked": False,
                "CommisionSplitPercent": 0.0,
                "Store": 1,  # Updated from 49 to 01
                "Email": "",
                "CustomNote": "",  # Best Contacts etc...
                "Note": self.scope_of_work,  # Description of works
                "WorkOrderNote": "",
                "PickingTicketNote": None,
                "OrderDate": "",
                "MeasureDate": "",  # Commencement date from extracted pdf data
                "PromiseDate": "",  # Completion date from extracted pdf data if available
                "PONumber": self.po_number,  # PO Number from extracted pdf data
                "CustomerType": "INSURANCE",
                "JobNumber": "",  # Supervisor name and phone number from extracted pdf data
                "DateEntered": datetime.now().strftime("%Y-%m-%d"),  # Today's date
                "DatePaid": None,
                "DueDate": "",
                "Model": None,
                "PriceLevel": 3,
                "TaxStatus": "Tax",
                "Occupied": False,
                "Voided": False,
                "AdSource": 1,
                "TaxCode": None,
                "OverheadMarginBase": None,
                "TaxStatusLocked": False,
                "Map": None,
                "Zone": None,
                "Phase": None,
                "Tract": None,
                "Block": None,
                "Lot": None,
                "Unit": None,
                "Property": None,
                "PSMemberNumber": 0,
                "PSMemberName": None,
                "PSBusinessName": None,
                "TaxMethod": "",
                "TaxInclusive": False,
                "UserOrderType": 12,
                "ServiceType": 9,
                "ContractType": 2,
                "Timeslot": 0,
                "InstallStore": 1,  # Updated from 49 to 01
                "AgeFrom": None,
                "Completed": None,
                "ReferralAmount": 0.0,
                "ReferralLocked": False,
                "PreAuthorization": None,
                "SalesTax": 0.0,
                "GrandInvoiceTotal": 0.0,
                "MaterialOnly": 0.0,
                "Labor": 0.0,
                "MiscCharges": float(self.dollar_value),  # Dollar Value from extracted pdf data
                "InvoiceTotal": 0.0,
                "MiscTax": 0.0,
                "RecycleFee": 0.0,
                "TotalPaid": 0.0,
                "Balance": 0.0,
                "DiscountRate": 0.0,
                "DiscountAmount": 0.0,
                "ApplyRecycleFee": False,
                "Attachements": None,  # Saved PDF
                "PendingAttachments": None,
                "Order": None,
                "LockInfo": None,
                "Message": None,
                "Lines": []
            },
            "products": None
        }
