import re
import logging
import os
import pdfplumber
import PyPDF2
import fitz  # PyMuPDF
import traceback
from typing import Dict, Optional, Any, Tuple, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from difflib import SequenceMatcher

# Configure logging
logger = logging.getLogger(__name__)

class BuilderType(Enum):
    AMBROSE = "Ambrose Construct Group"
    PROFILE = "Profile Build Group"
    CAMPBELL = "Campbell Construction"
    RIZON = "Rizon Group"
    AUSTRALIAN_RESTORATION = "Australian Restoration Company"
    TOWNSEND = "Townsend Building Services"
    ONE_SOLUTIONS = "One Solutions"
    UNKNOWN = "Unknown"

@dataclass
class TemplatePatterns:
    po_patterns: List[str]
    customer_patterns: List[str]
    description_patterns: List[str]
    dollar_patterns: List[str]
    supervisor_patterns: List[str]
    address_patterns: List[str]
    commencement_date_patterns: List[str] = None
    completion_date_patterns: List[str] = None
    supervisor_section_pattern: str = None

class TemplateDetector:
    def __init__(self):
        self.template_configs = {
            BuilderType.AMBROSE: TemplatePatterns(
                po_patterns=[
                    r"P\.O\.\s*No:?\s*(20\d{6}-\d{2})",
                    r"PO[:\s#]+(20\d{6}-\d{2})",
                    r"Purchase\s+Order[:\s#]+(20\d{6}-\d{2})",
                    r"Order\s+Number[:\s#]+(20\d{6}-\d{2})",
                ],
                customer_patterns=[
                    r"Insured\s+Owner:?\s*([A-Za-z\s]+?)(?=\n|Authorised)",
                    r"Insured:?\s*([A-Za-z\s]+?)(?=\n)",
                    r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                    r"Name[:\s]+([A-Za-z\s]+?)(?=\n)",
                    r"Bill\s+To[:\s]+([A-Za-z\s]+?)(?=\n)",
                ],
                description_patterns=[
                    r"Description\s+of\s+Works[:\s]*(.+?)(?=Supervisor|$)",
                    r"Works\s+Description[:\s]*(.+?)(?=Supervisor|$)",
                    r"Scope\s+of\s+Works[:\s]*(.+?)(?=Supervisor|$)",
                ],
                dollar_patterns=[
                    r"\$\s*([\d,]+\.?\d*)",
                    r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
                ],
                supervisor_patterns=[
                    r"Supervisor[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                    r"Project\s+Manager[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                ],
                address_patterns=[
                    r"Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                    r"Site\s+Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                ],
                supervisor_section_pattern=r"Supervisor\s+Details"
            ),
            BuilderType.PROFILE: TemplatePatterns(
                po_patterns=[
                    r"WORK\s+ORDER:?\s*(PBG-\d+-\d+)",
                    r"PBG-\d+-\d+",
                    r"Order\s+Number[:\s#]+(PBG-\d+-\d+)",
                    r"Contract\s+No[.:]?\s*(PBG-\d+-\d+)",
                ],
                customer_patterns=[
                    r"Client[:\s]+\n?([A-Za-z\s&]+?)(?=\n|Job)",
                    r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                    r"SITE\s+CONTACT[:\s]+([A-Za-z\s]+?)(?=\n)",
                ],
                description_patterns=[
                    r"NOTES[:\s]*\n([\s\S]+?)(?=All amounts|Total|$)",
                    r"Scope\s+of\s+Works[:\s]*(.+?)(?=All amounts|Total|$)",
                    r"PBG-\d+-\d+\s*\n([\s\S]+?)(?=All amounts|Total|$)",
                ],
                dollar_patterns=[
                    r"Total\s+AUD\s*\$?\s*([\d,]+\.?\d*)",
                    r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
                    r"\$\s*([\d,]+\.?\d*)",
                ],
                supervisor_patterns=[
                    r"Supervisor[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                    r"Project\s+Manager[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                ],
                address_patterns=[
                    r"Site\s+Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                    r"Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                ],
                supervisor_section_pattern=r"Supervisor[:\s]"
            ),
            BuilderType.CAMPBELL: TemplatePatterns(
                po_patterns=[
                    r"Contract\s+No[.:]?\s*(CCC\d+-\d+)",
                    r"CCC\d+-\d+",
                    r"CONTRACT\s+NO[.:]?\s*(CCC\d+-\d+)",
                    r"Contract\s+Number[.:]?\s*(CCC\d+-\d+)",
                ],
                customer_patterns=[
                    r"Customer:\s*\n([A-Za-z\s]+?)(?=\n)",
                    r"Site\s+Contact:\s*\n([A-Za-z\s]+?)(?:\s*-|$)",
                    r"Customer[:\s]+\n?([A-Za-z\s]+?)(?=\n|Site)",
                    r"Customer[:\s]+([A-Za-z\s]+)",
                    r"Client[:\s]+([A-Za-z\s]+?)(?=\n)",
                    r"Owner[:\s]+([A-Za-z\s]+?)(?=\n)",
                ],
                description_patterns=[
                    r"Scope\s+of\s+Work[:\s]*\n([\s\S]+?)(?=Totals|Page|Subtotal|$)",
                    r"CCC\d+-\d+[\s\S]+?Description[:\s]*\n([\s\S]+?)(?=Totals|Page|Subtotal|$)",
                    r"Description\s+of\s+Works[:\s]*(.+?)(?=Totals|Page|$)",
                ],
                dollar_patterns=[
                    r"Subtotal\s*\n\s*\$?([\d,]+\.?\d*)",
                    r"Subtotal\s+\$\s*([\d,]+\.?\d*)",
                    r"Total\s*\$?\s*([\d,]+\.?\d*)",
                    r"\$\s*([\d,]+\.?\d*)",
                ],
                supervisor_patterns=[
                    r"CONTRACTOR'S\s+REPRESENTATIVE[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                    r"Supervisor[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                ],
                address_patterns=[
                    r"Site\s+Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                    r"Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                ],
                supervisor_section_pattern=r"CONTRACTOR'S\s+REPRESENTATIVE|Supervisor"
            ),
            BuilderType.RIZON: TemplatePatterns(
                po_patterns=[
                    r"PURCHASE\s+ORDER\s+NO[:\s]*\n?(P?\d+)",
                    r"(P\d{6})",
                    r"ORDER\s+NUMBER[:\s]*(\d+/\d+/\d+)",
                    r"(\d{6}/\d{3}/\d{2})",
                    r"PO[:\s#]+(P?\d+)",
                ],
                customer_patterns=[
                    r"Client\s*/\s*Site\s+Details.*?\n(?:[^\n]+\n){3,6}([A-Z][A-Za-z\s]+?)(?=\n)",
                    r"Client\s*/\s*Site\s+Details[:\s]*\n?([A-Za-z\s]+?)(?=\n\d+|\n[A-Za-z]+\s+[A-Za-z]+,)",
                    r"Client\s*/\s*Site\s+Details[:\s]*\n?([A-Za-z\s]+?)(?=\n|\()",
                    r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                    r"Site\s+Details[:\s]*\n?([A-Za-z\s]+?)(?=\n)",
                ],
                description_patterns=[
                    r"SCOPE\s+OF\s+WORKS[:\s]*\n([\s\S]+?)(?=Net Order|PURCHASE\s+ORDER\s+CONDITIONS|Total|$)",
                    r"Scope\s+of\s+Works[:\s]*\n([\s\S]+?)(?=Net Order|Total|$)",
                ],
                dollar_patterns=[
                    r"Total\s+Order[:\s]*\$?\s*([\d,]+\.?\d*)",
                    r"Net\s+Order[:\s]*\$?\s*([\d,]+\.?\d*)",
                    r"\$\s*([\d,]+\.?\d*)",
                ],
                supervisor_patterns=[
                    r"Supervisor[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                    r"Project\s+Manager[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                ],
                address_patterns=[
                    r"Site\s+Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                    r"Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                ],
                supervisor_section_pattern=r"Supervisor[:\s]"
            ),
            BuilderType.AUSTRALIAN_RESTORATION: TemplatePatterns(
                po_patterns=[
                    r"Order\s+Number[:\s]*\n?(PO\d+-[A-Z0-9]+-\d+)",
                    r"PO\d+-[A-Z0-9]+-\d+",
                    r"Purchase\s+Order[:\s#]+(PO\d+-[A-Z0-9]+-\d+)",
                ],
                customer_patterns=[
                    r"Customer\s+Details[:\s]*\n?([A-Za-z\s]+?)(?=\n|Site)",
                    r"Customer\s+Details[:\s]*([A-Za-z\s]+)",
                    r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                    r"Client[:\s]+([A-Za-z\s]+?)(?=\n)",
                ],
                description_patterns=[
                    r"Flooring\s+Contractor\s+Material\n([\s\S]+?)(?=All amounts|Preliminaries|Total|$)",
                    r"<highlighter Header>\s*=?\s*([\s\S]+?)(?=All amounts shown|Total|$)",
                    r"Scope\s+of\s+Works[:\s]*\n([\s\S]+?)(?=All amounts|Total|$)",
                ],
                dollar_patterns=[
                    r"Sub\s+Total\s+\$\s*([\d,]+\.?\d*)",
                    r"Total\s+AUD\s*\$?\s*([\d,]+\.?\d*)",
                    r"\$\s*([\d,]+\.?\d*)",
                ],
                supervisor_patterns=[
                    r"Project\s+Manager[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                    r"Case\s+Manager[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                ],
                address_patterns=[
                    r"Site\s+Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                    r"Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                ],
                supervisor_section_pattern=r"Project\s+Manager[:\s]|Case\s+Manager[:\s]"
            ),
            BuilderType.TOWNSEND: TemplatePatterns(
                po_patterns=[
                    r"Order\s+Number\s*\n\s*([A-Z0-9]+)",
                    r"Purchase\s+Order[:\s#]+(TBS-\d+)",
                    r"TBS-\d+",
                    r"Order\s+Number[:\s]*(TBS-\d+|PO\d+)",
                    r"WO[:\s#]+(\d+)",
                    r"Work\s+Order[:\s#]+(\d+)",
                ],
                customer_patterns=[
                    r"Site\s+Contact\s+Name\s*\n([A-Za-z\s\(\)]+?)(?=\n)",
                    r"Site\s+Contact\s+name\s*=?\s*([A-Za-z\s]+?)(?=\n|Subtotal)",
                    r"Contact\s+Name\s*\n\s*([A-Za-z\s]+?)(?=\n)",
                    r"Attention[:\s]+([A-Za-z\s]+?)(?=\n|Email)",
                    r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                    r"Client[:\s]+([A-Za-z\s]+?)(?=\n)",
                ],
                description_patterns=[
                    r"(?:Flooring|Floor\s+Preperation)[^<]*?([\s\S]+?)(?=Total|$)",
                    r"Additional\s+Notes/Instructions[:\s]*\n([\s\S]+?)(?=Flooring|Floor|Start|$)",
                    r"Scope\s+of\s+Works[:\s]*\n([\s\S]+?)(?=Total|ABN|Page|$)",
                    r"Work\s+Description[:\s]*\n([\s\S]+?)(?=Total|ABN|Page|$)",
                    r"Description[:\s]*\n([\s\S]+?)(?=Total|ABN|Page|$)",
                ],
                dollar_patterns=[
                    r"Subtotal\s*\n\s*\$?([\d,]+\.?\d*)",
                    r"Subtotal\s*=?\s*\$?\s*([\d,]+\.?\d*)",
                    r"Total\s+Inc\.?\s+GST[:\s]*\$?\s*([\d,]+\.?\d*)",
                    r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
                    r"\$\s*([\d,]+\.?\d*)",
                ],
                supervisor_patterns=[
                    r"Project\s+Manager[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                    r"Supervisor[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                    r"Manager[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                ],
                address_patterns=[
                    r"Site\s+Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                    r"Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                ],
                supervisor_section_pattern=r"Project\s+Manager[:\s]|Supervisor[:\s]|Manager[:\s]"
            ),
            BuilderType.ONE_SOLUTIONS: TemplatePatterns(
                po_patterns=[
                    r"Purchase\s+Order\s+Number[:\s]+([A-Z0-9-]+)",
                    r"Order\s+Number[:\s]+([A-Z0-9-]+)",
                    r"PO[:\s]+([A-Z0-9-]+)",
                ],
                customer_patterns=[
                    r"Site\s+Contact\s+Name[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                    r"Customer[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                    r"Client[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                ],
                description_patterns=[
                    r"Floor\s+Covers[\s\n]+([\s\S]+?)(?=Totals|Total|$)",
                    r"Scope\s+of\s+Works[:\s]+([\s\S]+?)(?=Totals|Total|$)",
                ],
                dollar_patterns=[
                    r"Subtotal[\s:]*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)",
                    r"Total[\s:]*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)",
                    r"\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
                ],
                supervisor_patterns=[
                    r"One\s+Solution\s+Representative[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                    r"Supervisor[:\s]+([A-Za-z\s]+?)(?=\n|$)",
                ],
                address_patterns=[
                    r"Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                    r"Site\s+Address[:\s]+([^\n]+(?:\n[^\n]+){0,2})",
                ],
                commencement_date_patterns=[
                    r"Works\s+to\s+Commence[\s\n]+([^\n]+)",
                    r"Start\s+Date[\s\n]+([^\n]+)",
                ],
                completion_date_patterns=[
                    r"Works\s+to\s+be\s+Completed\s+By[\s\n]+([^\n]+)",
                    r"Completion\s+Date[\s\n]+([^\n]+)",
                ],
                supervisor_section_pattern=r"One\s+Solution\s+Representative[:\s]|Supervisor[:\s]"
            )
        }

    def detect_template(self, text: str) -> Tuple[BuilderType, Optional[TemplatePatterns]]:
        """
        Detect the template type based on the content of the PDF text.
        Returns a tuple of (BuilderType, TemplatePatterns)
        """
        # First try to detect by PO number pattern
        for builder_type, patterns in self.template_configs.items():
            for po_pattern in patterns.po_patterns:
                if re.search(po_pattern, text, re.IGNORECASE | re.MULTILINE):
                    return builder_type, patterns

        # If no PO pattern match, try to detect by company name mentions
        company_indicators = {
            BuilderType.AMBROSE: ['Ambrose Construct', 'Ambrose Group'],
            BuilderType.PROFILE: ['Profile Build', 'PBG'],
            BuilderType.CAMPBELL: ['Campbell Construction', 'CCC'],
            BuilderType.RIZON: ['Rizon Group', 'Rizon'],
            BuilderType.AUSTRALIAN_RESTORATION: ['Australian Restoration', 'ARC'],
            BuilderType.TOWNSEND: ['Townsend Building', 'TBS'],
            BuilderType.ONE_SOLUTIONS: ['One Solutions', 'A To Z Flooring Solutions']
        }

        for builder_type, indicators in company_indicators.items():
            if any(indicator.lower() in text.lower() for indicator in indicators):
                return builder_type, self.template_configs[builder_type]

        return BuilderType.UNKNOWN, None

    def get_patterns(self, builder_type: BuilderType) -> Optional[TemplatePatterns]:
        """
        Get the template patterns for a specific builder type.
        """
        return self.template_configs.get(builder_type)

    def extract_field(self, text: str, patterns: List[str]) -> Optional[str]:
        """
        Extract a field from text using the provided patterns.
        Returns the first non-None capture group if multiple groups exist.
        """
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                # Get all groups and return the first non-None one
                groups = match.groups()
                for group in groups:
                    if group is not None:
                        return group.strip()
        return None

    def extract_dollar_value(self, text: str, patterns: List[str]) -> Optional[float]:
        """
        Extract and convert dollar value from text using the provided patterns.
        """
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    return float(value_str)
                except ValueError:
                    continue
        return None

class PDFExtractor:
    def __init__(self):
        self.template_detector = TemplateDetector()

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text from PDF file using multiple methods for reliability.
        """
        text = ""
        methods = [
            self._extract_with_pymupdf,
            self._extract_with_pdfplumber,
            self._extract_with_pypdf2
        ]

        for method in methods:
            try:
                text = method(pdf_path)
                if text and len(text.strip()) > 0:
                    logger.info(f"Successfully extracted text using {method.__name__}")
                    break
            except Exception as e:
                logger.warning(f"Failed to extract text using {method.__name__}: {str(e)}")

        if not text:
            logger.error("All PDF extraction methods failed")
            return ""

        # Debug: Print first 2500 characters of extracted text
        logger.debug("\n=== EXTRACTED TEXT SAMPLE ===")
        logger.debug(text[:2500])
        logger.debug("=== END OF EXTRACTED TEXT SAMPLE ===\n")

        return text

    def _extract_with_pymupdf(self, pdf_path: str) -> str:
        """
        Extract text using PyMuPDF (fitz).
        """
        text = ""
        try:
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    text += page.get_text()
        except Exception as e:
            logger.error(f"PyMuPDF extraction failed: {str(e)}")
        return text

    def _extract_with_pdfplumber(self, pdf_path: str) -> str:
        """
        Extract text using pdfplumber.
        """
        text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() + "\n"
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {str(e)}")
        return text

    def _extract_with_pypdf2(self, pdf_path: str) -> str:
        """
        Extract text using PyPDF2.
        """
        text = ""
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
        except Exception as e:
            logger.error(f"PyPDF2 extraction failed: {str(e)}")
        return text

    def parse_address(self, address_text: str) -> Dict[str, str]:
        """
        Parse address text into components.
        """
        address_parts = {
            'address1': '',
            'address2': '',
            'city': '',
            'state': '',
            'postal_code': ''
        }

        if not address_text:
            return address_parts

        # Split address into lines
        lines = [line.strip() for line in address_text.split('\n') if line.strip()]
        
        if not lines:
            return address_parts

        # First line is usually street address
        address_parts['address1'] = lines[0]

        # Second line might be additional address info
        if len(lines) > 1:
            address_parts['address2'] = lines[1]

        # Last line usually contains city, state, and postal code
        if len(lines) > 2:
            last_line = lines[-1]
            # Try to match state and postal code pattern
            state_postal_match = re.search(r'([A-Z]{2,3})\s+(\d{4})', last_line)
            if state_postal_match:
                address_parts['state'] = state_postal_match.group(1)
                address_parts['postal_code'] = state_postal_match.group(2)
                # City is everything before the state
                city = last_line[:state_postal_match.start()].strip()
                address_parts['city'] = city

        return address_parts

    def parse_name(self, name_text: str) -> Dict[str, str]:
        """
        Parse full name into first and last name.
        """
        name_parts = {
            'first_name': '',
            'last_name': ''
        }

        if not name_text:
            return name_parts

        # Split name into parts
        parts = name_text.strip().split()
        if len(parts) >= 2:
            name_parts['first_name'] = parts[0]
            name_parts['last_name'] = ' '.join(parts[1:])
        elif len(parts) == 1:
            name_parts['last_name'] = parts[0]

        return name_parts

    def extract_data_from_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract data from PDF using template detection.
        """
        # Extract text from PDF
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            return {'error': 'Failed to extract text from PDF'}

        # Debug: Print first 2500 characters of extracted text
        logger.debug("\n=== EXTRACTED TEXT SAMPLE ===")
        logger.debug(text[:2500])
        logger.debug("=== END OF EXTRACTED TEXT SAMPLE ===\n")

        # Detect template type
        builder_type, patterns = self.template_detector.detect_template(text)
        if not patterns:
            return {'error': 'Unknown template type'}

        # Debug: Print detected template type and patterns
        logger.info(f"Detected template type: {builder_type.value}")
        logger.debug(f"Using patterns: {patterns}")

        # Extract data using template patterns
        extracted_data = {
            'builder_type': builder_type.value,
            'po_number': self.template_detector.extract_field(text, patterns.po_patterns),
            'dollar_value': self.template_detector.extract_dollar_value(text, patterns.dollar_patterns),
            'description_of_works': self.template_detector.extract_field(text, patterns.description_patterns),
            'supervisor_name': self.template_detector.extract_field(text, patterns.supervisor_patterns)
        }

        # Debug: Print extracted fields
        logger.debug("\nExtracted fields:")
        for key, value in extracted_data.items():
            logger.debug(f"{key}: {value}")

        # Extract and parse customer name
        customer_name = self.template_detector.extract_field(text, patterns.customer_patterns)
        if customer_name:
            name_parts = self.parse_name(customer_name)
            extracted_data.update(name_parts)
            logger.debug(f"Customer name parts: {name_parts}")

        # Extract and parse address
        address_text = self.template_detector.extract_field(text, patterns.address_patterns)
        if address_text:
            address_parts = self.parse_address(address_text)
            extracted_data.update(address_parts)
            logger.debug(f"Address parts: {address_parts}")

        # Extract dates if patterns exist
        if patterns.commencement_date_patterns:
            commencement_date = self.template_detector.extract_field(text, patterns.commencement_date_patterns)
            if commencement_date:
                extracted_data['commencement_date'] = commencement_date
                logger.debug(f"Commencement date: {commencement_date}")

        if patterns.completion_date_patterns:
            completion_date = self.template_detector.extract_field(text, patterns.completion_date_patterns)
            if completion_date:
                extracted_data['completion_date'] = completion_date
                logger.debug(f"Completion date: {completion_date}")

        # Extract phone numbers (common pattern across templates)
        phone_patterns = [
            r'Phone:\s*(\d[\d\s-]+)',
            r'Mobile:\s*(\d[\d\s-]+)',
            r'Contact\s+No\.:\s*(\d[\d\s-]+)',
            r'Phone1:\s*(\d[\d\s-]+)',
            r'Phone2:\s*(\d[\d\s-]+)',
            r'Home:\s*(\d[\d\s-]+)',
            r'Work:\s*(\d[\d\s-]+)'
        ]

        phones = []
        for pattern in phone_patterns:
            phone = self.template_detector.extract_field(text, [pattern])
            if phone:
                phones.append(phone)
                logger.debug(f"Found phone: {phone}")

        if phones:
            extracted_data['phone'] = phones[0]
            if len(phones) > 1:
                extracted_data['mobile'] = phones[1]
            if len(phones) > 2:
                extracted_data['extra_phones'] = phones[2:]

        # Extract email (common pattern across templates)
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        email_match = re.search(email_pattern, text)
        if email_match:
            extracted_data['email'] = email_match.group(0)
            logger.debug(f"Found email: {email_match.group(0)}")

        # Debug: Print final extracted data
        logger.debug("\nFinal extracted data:")
        for key, value in extracted_data.items():
            logger.debug(f"{key}: {value}")

        return extracted_data 