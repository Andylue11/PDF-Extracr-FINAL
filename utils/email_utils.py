"""
Email utility module for sending emails via SMTP.
"""
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

logger = logging.getLogger(__name__)


class EmailSender:
    """Handle email sending functionality."""
    
    def __init__(self):
        """Initialize email sender with configuration from environment."""
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
        
        # Check if email is configured
        self.is_configured = all([
            self.smtp_server,
            self.smtp_port,
            self.smtp_username,
            self.smtp_password
        ])
        
        if not self.is_configured:
            logger.warning("Email configuration incomplete. Email functionality will be disabled.")
    
    def send_email(self, to_email, subject, body, cc_emails=None, attachments=None):
        """
        Send an email with optional CC and attachments.
        
        Args:
            to_email (str): Recipient email address
            subject (str): Email subject
            body (str): Email body (HTML supported)
            cc_emails (list): List of CC email addresses
            attachments (list): List of file paths to attach
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.error("Email not configured. Cannot send email.")
            return False
            
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            
            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)
            
            # Add body
            msg.attach(MIMEText(body, 'html'))
            
            # Add attachments
            if attachments:
                for file_path in attachments:
                    if os.path.isfile(file_path):
                        self._attach_file(msg, file_path)
            
            # Connect to server and send
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                
                # Get all recipients
                recipients = [to_email]
                if cc_emails:
                    recipients.extend(cc_emails)
                
                server.send_message(msg, to_addrs=recipients)
                
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def _attach_file(self, msg, file_path):
        """Attach a file to the email message."""
        try:
            with open(file_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                
            encoders.encode_base64(part)
            filename = os.path.basename(file_path)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )
            
            msg.attach(part)
        except Exception as e:
            logger.error(f"Failed to attach file {file_path}: {str(e)}")
    
    def send_job_creation_notification(self, job_data, recipient_email):
        """
        Send a notification email when a job is created.
        
        Args:
            job_data (dict): Job data including PO number, customer info, etc.
            recipient_email (str): Email address to send notification to
            
        Returns:
            bool: True if email sent successfully
        """
        subject = f"Job Created - PO #{job_data.get('po_number', 'N/A')}"
        
        body = f"""
        <html>
            <body>
                <h2>Job Created Successfully</h2>
                <p>A new job has been created in RFMS with the following details:</p>
                
                <h3>Job Information</h3>
                <ul>
                    <li><strong>PO Number:</strong> {job_data.get('po_number', 'N/A')}</li>
                    <li><strong>Job ID:</strong> {job_data.get('job_id', 'N/A')}</li>
                    <li><strong>Customer:</strong> {job_data.get('customer_name', 'N/A')}</li>
                    <li><strong>Value:</strong> ${job_data.get('dollar_value', 0):.2f}</li>
                    <li><strong>Date Created:</strong> {job_data.get('date_created', 'N/A')}</li>
                </ul>
                
                <h3>Work Details</h3>
                <p><strong>Description:</strong><br>
                {job_data.get('description_of_works', 'N/A')}</p>
                
                <p>This is an automated notification from RFMS PDF XTRACR.</p>
            </body>
        </html>
        """
        
        return self.send_email(recipient_email, subject, body)


# Create a singleton instance
email_sender = EmailSender() 