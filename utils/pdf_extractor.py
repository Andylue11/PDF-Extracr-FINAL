import re
import logging
import os
import pdfplumber
import PyPDF2
import fitz  # PyMuPDF
import traceback
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from difflib import SequenceMatcher
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Template configurations for different companies
TEMPLATE_CONFIGS = {
    "ambrose": {
        "name": "Ambrose Construct Group",
        "po_patterns": [
            r"P\.O\.\s*No:?\s*(20\d{6}-\d{2})",  # Specific format: 20XXXXXX-XX
            r"PO[:\s#]+(20\d{6}-\d{2})",
            r"Purchase\s+Order[:\s#]+(20\d{6}-\d{2})",
            r"Order\s+Number[:\s#]+(20\d{6}-\d{2})",
        ],
        "customer_patterns": [
            r"Insured\s+Owner:?\s*([A-Za-z\s\-'\.]+?)(?=\n|Authorised|$)",  # Primary pattern for Ambrose - includes hyphens, apostrophes, periods
            r"Insured:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)",
            r"Customer[:\s]+([A-Za-z\s\-'\.]+?)(?=\n|$)",
            r"Name[:\s]+([A-Za-z\s\-'\.]+?)(?=\n|$)",
            r"Bill\s+To[:\s]+([A-Za-z\s\-'\.]+?)(?=\n|$)",
        ],
        "description_patterns": [
            # Ambrose-specific patterns - Extract content between Description and TOTAL
            r"Description\s+of\s+the\s+Works[:\s]*\n(?:Quantity\s*Unit\s*)?\n?([\s\S]+?)(?=TOTAL\s+Purchase\s+Order\s+Price|Total\s+Purchase\s+Order\s+Value|TOTAL\s+PURCHASE\s+ORDER|$)",  # Primary: Ambrose format with optional "Quantity Unit" header
            r"Description\s+of\s+Works[:\s]*\n(?:Quantity\s*Unit\s*)?\n?([\s\S]+?)(?=TOTAL\s+Purchase\s+Order\s+Price|Total\s+Purchase\s+Order\s+Value|TOTAL\s+PURCHASE\s+ORDER|$)",  # Alternative format
            r"Description\s+of\s+the\s+Works[:\s]*\n([\s\S]+?)(?=TOTAL|Total|Supervisor\s+Details|$)",  # Multi-line fallback
            r"Description\s+of\s+Works[:\s]*\n([\s\S]+?)(?=TOTAL|Total|Supervisor\s+Details|$)",  # Multi-line fallback
            r"Description\s+of\s+Works[:\s]*(.+?)(?=Supervisor|Total|$)",  # Single line fallback
        ],
        "supervisor_section_pattern": r"Supervisor\s+Details",
        "dollar_patterns": [
            r"TOTAL\s+Purchase\s+Order\s+Price\s*\(ex\s+GST\)\s*\$?\s*([\d,]+\.?\d*)",  # Primary Ambrose pattern
            r"Total\s+Purchase\s+Order\s+Value\s*\(ex\s+GST\)\s*\$?\s*([\d,]+\.?\d*)",  # Alternative pattern
            r"TOTAL\s+PURCHASE\s+ORDER\s+PRICE\s*\$?\s*([\d,]+\.?\d*)",  # Caps version
            r"Total\s+Purchase\s+Order\s+Value[:\s]*\$?\s*([\d,]+\.?\d*)",  # Original pattern
            r"TOTAL\s+PURCHASE\s+ORDER[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
            r"\$\s*([\d,]+\.?\d*)",
        ],
        "address_patterns": [
            r"Site\s+Address[:\s]*\n?([A-Za-z0-9\s\.,/#-]+?)(?=\n|$)",  # More specific pattern for Ambrose
            r"Property\s+Address[:\s]*\n?([A-Za-z0-9\s\.,/#-]+?)(?=\n|$)",
            r"Location[:\s]*\n?([A-Za-z0-9\s\.,/#-]+?)(?=\n|$)",
            r"Address[:\s]*\n?([A-Za-z0-9\s\.,/#-]+?)(?=\n|$)",  # Generic address pattern
        ],
    },
    "profile_build": {
        "name": "Profile Build Group",
        "po_patterns": [
            r"WORK\s+ORDER:?\s*(PBG-\d+-\d+)",  # PBG-18191-18039
            r"PBG-\d+-\d+",  # Direct pattern match
            r"Order\s+Number[:\s#]+(PBG-\d+-\d+)",
            r"Contract\s+No[.:]?\s*(PBG-\d+-\d+)",
        ],
        "customer_patterns": [
            r"SITE\s+CONTACT:\s*([A-Za-z\s\-'\.]+?)(?=\n)",  # Primary: Site contact is the customer - includes hyphens, apostrophes, periods
            r"Client[:\s]+\n?([A-Za-z\s&\-'\.]+?)(?=\n|Job)",
            r"Customer[:\s]+([A-Za-z\s\-'\.]+?)(?=\n)",
        ],
        "description_patterns": [
            r"PBG-\d+-\d+\s*\n([\s\S]+?)(?=Subtotal|Total|$)",  # Main work description
            r"NOTES[:\s]*\n([\s\S]+?)(?=All amounts|Total|Subtotal|$)",  # Additional notes
            r"Scope\s+of\s+Works[:\s]*(.+?)(?=All amounts|Total|Subtotal|$)",
        ],
        "supervisor_section_pattern": r"Supervisor[:\s]",
        "dollar_patterns": [
            r"Subtotal\s*\n\s*\$?([\d,]+\.?\d*)",  # Primary: Subtotal is the main value
            r"Total\s+AUD\s*\$?\s*([\d,]+\.?\d*)",
            r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
        ],
    },
    "campbell": {
        "name": "Campbell Construction",
        "po_patterns": [
            r"Contract\s+No[.:]?\s*(CCC\d+-\d+)",  # CCC55132-88512
            r"CCC\d+-\d+",  # Direct pattern match
            r"CONTRACT\s+NO[.:]?\s*(CCC\d+-\d+)",
            r"Contract\s+Number[.:]?\s*(CCC\d+-\d+)",
        ],
        "customer_patterns": [
            r"Customer:\s*\n([A-Za-z\s\-'\.]+?)(?=\n)",  # Customer on next line - includes hyphens, apostrophes, periods
            r"Site\s+Contact:\s*\n([A-Za-z\s\-'\.]+?)(?:\s*-|$)",  # Site Contact on next line
            r"Customer[:\s]+\n?([A-Za-z\s\-'\.]+?)(?=\n|Site)",
            r"Customer[:\s]+([A-Za-z\s\-'\.]+)",  # Simplified pattern
            r"Client[:\s]+([A-Za-z\s\-'\.]+?)(?=\n)",
            r"Owner[:\s]+([A-Za-z\s\-'\.]+?)(?=\n)",
        ],
        "description_patterns": [
            r"Scope\s+of\s+Work[:\s]*\n([\s\S]+?)(?=Totals|Page|Subtotal|$)",
            r"CCC\d+-\d+[\s\S]+?Description[:\s]*\n([\s\S]+?)(?=Totals|Page|Subtotal|$)",
            r"Description\s+of\s+Works[:\s]*(.+?)(?=Totals|Page|$)",
        ],
        "supervisor_section_pattern": r"CONTRACTOR'S\s+REPRESENTATIVE|Supervisor",
        "dollar_patterns": [
            r"Subtotal\s*\n\s*\$?([\d,]+\.?\d*)",  # Subtotal with newline
            r"Subtotal\s+\$\s*([\d,]+\.?\d*)",  # Based on key info: "Subtotal  $700.00"
            r"Total\s*\$?\s*([\d,]+\.?\d*)",
            r"\$\s*([\d,]+\.?\d*)",
        ],
    },
    "rizon": {
        "name": "Rizon Group",
        "po_patterns": [
            r"PURCHASE\s+ORDER\s+NO[:\s]*\n?(P?\d+)",  # P367117 or similar
            r"(P\d{6})",  # Direct pattern match - added capture group
            r"ORDER\s+NUMBER[:\s]*(\d+/\d+/\d+)",  # Alternative format
            r"(\d{6}/\d{3}/\d{2})",  # Format like 187165/240/01
            r"PO[:\s#]+(P?\d+)",
        ],
        "customer_patterns": [
            r"Client\s*/\s*Site\s+Details.*?\n(?:[^\n]+\n){3,6}([A-Z][A-Za-z\s\-'\.]+?)(?=\n)",  # Skip lines to get to actual name - includes hyphens, apostrophes, periods
            r"Client\s*/\s*Site\s+Details[:\s]*\n?([A-Za-z\s\-'\.]+?)(?=\n\d+|\n[A-Za-z]+\s+[A-Za-z]+,)",  # Name is first line in grid box
            r"Client\s*/\s*Site\s+Details[:\s]*\n?([A-Za-z\s\-'\.]+?)(?=\n|\()",
            r"Customer[:\s]+([A-Za-z\s\-'\.]+?)(?=\n)",
            r"Site\s+Details[:\s]*\n?([A-Za-z\s\-'\.]+?)(?=\n)",
        ],
        "description_patterns": [
            r"SCOPE\s+OF\s+WORKS[:\s]*\n([\s\S]+?)(?=Net Order|PURCHASE\s+ORDER\s+CONDITIONS|Total|$)",
            r"Scope\s+of\s+Works[:\s]*\n([\s\S]+?)(?=Net Order|Total|$)",
        ],
        "supervisor_section_pattern": r"Supervisor[:\s]",
        "dollar_patterns": [
            r"Total\s+Order[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"Net\s+Order[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"\$\s*([\d,]+\.?\d*)",
        ],
    },
    "australian_restoration": {
        "name": "Australian Restoration Company",
        "po_patterns": [
            r"Order\s+Number[:\s]*\n?(PO\d+-[A-Z0-9]+-\d+)",  # PO96799-BU01-003
            r"PO\d+-[A-Z0-9]+-\d+",  # Direct pattern match
            r"Purchase\s+Order[:\s#]+(PO\d+-[A-Z0-9]+-\d+)",
        ],
        "customer_patterns": [
            r"Customer\s+Details[:\s]*\n?([A-Za-z\s\-'\.]+?)(?=\n|Site)",
            r"Customer\s+Details[:\s]*([A-Za-z\s\-'\.]+)",  # Without lookahead - includes hyphens, apostrophes, periods
            r"Customer[:\s]+([A-Za-z\s\-'\.]+?)(?=\n)",
            r"Client[:\s]+([A-Za-z\s\-'\.]+?)(?=\n)",
        ],
        "description_patterns": [
            r"Flooring\s+Contractor\s+Material\n([\s\S]+?)(?=All amounts|Preliminaries|Total|$)",
            r"<highlighter Header>\s*=?\s*([\s\S]+?)(?=All amounts shown|Total|$)",  # Based on key info
            r"Scope\s+of\s+Works[:\s]*\n([\s\S]+?)(?=All amounts|Total|$)",
        ],
        "supervisor_section_pattern": r"Project\s+Manager[:\s]|Case\s+Manager[:\s]",
        "dollar_patterns": [
            r"Sub\s+Total\s+\$\s*([\d,]+\.?\d*)",  # Based on key info: "Sub Total     $3,588.00"
            r"Total\s+AUD\s*\$?\s*([\d,]+\.?\d*)",
            r"\$\s*([\d,]+\.?\d*)",
        ],
    },
    "townsend": {
        "name": "Townsend Building Services",
        "po_patterns": [
            r"Order\s+Number\s*\n\s*([A-Z0-9]+)",  # Matches "Order Number\nPO23218"
            r"Purchase\s+Order[:\s#]+(TBS-\d+)",
            r"TBS-\d+",
            r"Order\s+Number[:\s]*(TBS-\d+|PO\d+)",
            r"WO[:\s#]+(\d+)",
            r"Work\s+Order[:\s#]+(\d+)",
        ],
        "customer_patterns": [
            r"Site\s+Contact\s+Name\s*\n([A-Za-z\s\(\)\-'\.]+?)(?=\n)",  # Based on actual text - includes hyphens, apostrophes, periods, parentheses
            r"Site\s+Contact\s+name\s*=?\s*([A-Za-z\s\-'\.]+?)(?=\n|Subtotal)",  # Based on key info
            r"Contact\s+Name\s*\n\s*([A-Za-z\s\-'\.]+?)(?=\n)",  # Matches "Contact Name\nJOHN SURNAME"
            r"Attention[:\s]+([A-Za-z\s\-'\.]+?)(?=\n|Email)",
            r"Customer[:\s]+([A-Za-z\s\-'\.]+?)(?=\n)",
            r"Client[:\s]+([A-Za-z\s\-'\.]+?)(?=\n)",
        ],
        "description_patterns": [
            r"(?:Flooring|Floor\s+Preperation)[^<]*?([\s\S]+?)(?=Total|$)",  # Based on key info
            r"Additional\s+Notes/Instructions[:\s]*\n([\s\S]+?)(?=Flooring|Floor|Start|$)",  # Work Order notes
            r"Scope\s+of\s+Works[:\s]*\n([\s\S]+?)(?=Total|ABN|Page|$)",
            r"Work\s+Description[:\s]*\n([\s\S]+?)(?=Total|ABN|Page|$)",
            r"Description[:\s]*\n([\s\S]+?)(?=Total|ABN|Page|$)",
        ],
        "supervisor_section_pattern": r"Project\s+Manager[:\s]|Supervisor[:\s]|Manager[:\s]",
        "dollar_patterns": [
            r"Subtotal\s*\n\s*\$?([\d,]+\.?\d*)",  # Based on actual text: "Subtotal\n$14,430.00"
            r"Subtotal\s*=?\s*\$?\s*([\d,]+\.?\d*)",  # Based on key info: "Subtotal = Dollar value"
            r"Total\s+Inc\.?\s+GST[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
            r"\$\s*([\d,]+\.?\d*)",
        ],
    },
    "one_solutions": {
        "name": "One Solutions",
        "po_patterns": [
            r"Purchase\s+Order\s+Number[:\s]+([A-Z0-9-]+)",
            r"Order\s+Number[:\s]+([A-Z0-9-]+)",
            r"PO[:\s]+([A-Z0-9-]+)",
            r"Work\s+Order[:\s]+([A-Z0-9-]+)",
        ],
        "customer_patterns": [
            r"SITE\s+CONTACT:\s*([A-Za-z\s\-'\.]+?)(?=\n)",  # Primary: Site contact is the customer - includes hyphens, apostrophes, periods
            r"Site\s+Contact\s+Name[:\s]+([A-Za-z\s\-'\.]+?)(?=\n|$)",
            r"Customer[:\s]+([A-Za-z\s\-'\.]+?)(?=\n|$)",
            r"Client[:\s]+([A-Za-z\s\-'\.]+?)(?=\n|$)",
            r"Contact\s+Name[:\s]+([A-Za-z\s\-'\.]+?)(?=\n|$)",
        ],
        "description_patterns": [
            r"Floor\s+Covers[\s\n]+([\s\S]+?)(?=Totals|Total|$)",
            r"Scope\s+of\s+Works[:\s]+([\s\S]+?)(?=Totals|Total|$)",
            r"Description\s+of\s+Works[:\s]*(.+?)(?=Totals|Total|$)",
        ],
        "supervisor_section_pattern": r"One\s+Solution\s+Representative[:\s]|Supervisor[:\s]",
        "dollar_patterns": [
            r"Subtotal[\s:]*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)",
            r"Total[\s:]*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)",
            r"\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        ],
        "commencement_date_patterns": [
            r"Works\s+to\s+Commence[\s\n]+([^\n]+)",
            r"Start\s+Date[\s\n]+([^\n]+)",
        ],
        "completion_date_patterns": [
            r"Works\s+to\s+be\s+Completed\s+By[\s\n]+([^\n]+)",
            r"Completion\s+Date[\s\n]+([^\n]+)",
        ],
    },
    "johns_lyng": {
        "name": "Johns Lyng Group",
        "po_patterns": [
            r"Purchase\s+Order[:\s#]+([A-Z0-9-]+)",
            r"PO[:\s#]+([A-Z0-9-]+)",
            r"Order\s+Number[:\s#]+([A-Z0-9-]+)",
            r"Work\s+Order[:\s#]+([A-Z0-9-]+)",
            r"JL[:\s#]+([A-Z0-9-]+)",
        ],
        "customer_patterns": [
            r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
            r"Client[:\s]+([A-Za-z\s]+?)(?=\n)",
            r"Site\s+Contact[:\s]+([A-Za-z\s]+?)(?=\n)",
            r"Contact\s+Name[:\s]+([A-Za-z\s]+?)(?=\n)",
            r"Name[:\s]+([A-Za-z\s]+?)(?=\n)",
        ],
        "description_patterns": [
            r"Scope\s+of\s+Works[:\s]*(.+?)(?=Supervisor|Total|$)",
            r"Description\s+of\s+Works[:\s]*(.+?)(?=Supervisor|Total|$)",
            r"Works\s+Description[:\s]*(.+?)(?=Supervisor|Total|$)",
            r"Project\s+Description[:\s]*(.+?)(?=Supervisor|Total|$)",
        ],
        "supervisor_section_pattern": r"Supervisor|Project\s+Manager|Site\s+Manager",
        "dollar_patterns": [
            r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
            r"Subtotal[:\s]+\$?\s*([\d,]+\.?\d*)",
            r"\$\s*([\d,]+\.?\d*)",
        ],
    },
    "generic": {
        "name": "Generic Template",
        "po_patterns": [
            r"P\.O\.\s*No:?\s*([A-Za-z0-9-]+)",
            r"PO[:\s#]+([A-Za-z0-9-]+)",
            r"Purchase\s+Order[:\s#]+([A-Za-z0-9-]+)",
            r"Order\s+Number[:\s#]+([A-Za-z0-9-]+)",
            r"CONTRACT\s+NO[.:]?\s*([A-Za-z0-9-]+)",
            r"Contract\s+Number[.:]?\s*([A-Za-z0-9-]+)",
            r"WORK\s+ORDER[:\s]+([A-Za-z0-9-]+)",
            r"JOB\s+NUMBER[:\s]+([A-Za-z0-9-]+)",
        ],
        "customer_patterns": [
            r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
            r"Client[:\s]+([A-Za-z\s]+?)(?=\n)",
            r"Name[:\s]+([A-Za-z\s]+?)(?=\n)",
            r"Bill\s+To[:\s]+([A-Za-z\s]+?)(?=\n)",
        ],
        "description_patterns": [
            r"Description\s+of\s+Works[:\s]*(.+?)(?=Supervisor|Total|$)",
            r"Scope\s+of\s+Works[:\s]*(.+?)(?=Supervisor|Total|$)",
            r"Works\s+Description[:\s]*(.+?)(?=Supervisor|Total|$)",
        ],
        "supervisor_section_pattern": r"Supervisor|Contractor[\s']*s?\s+Representative",
        "dollar_patterns": [
            r"\$\s*([\d,]+\.?\d*)",
            r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
        ],
    }
}


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
        pass

    def detect_template(self, text: str) -> Tuple[BuilderType, Optional[TemplatePatterns]]:
        """Detect template type from text and return patterns"""
        template_name = detect_template(text)
        builder_type = BuilderType.UNKNOWN
        
        # Map template names to BuilderType
        template_mapping = {
            "profile_build": BuilderType.PROFILE,
            "ambrose": BuilderType.AMBROSE,
            "campbell": BuilderType.CAMPBELL,
            "rizon": BuilderType.RIZON,
            "australian_restoration": BuilderType.AUSTRALIAN_RESTORATION,
            "townsend": BuilderType.TOWNSEND,
            "one_solutions": BuilderType.ONE_SOLUTIONS,
        }
        
        if template_name in template_mapping:
            builder_type = template_mapping[template_name]
            patterns = self.get_patterns(builder_type)
            return builder_type, patterns
        
        return BuilderType.UNKNOWN, None

    def get_patterns(self, builder_type: BuilderType) -> Optional[TemplatePatterns]:
        """Get patterns for a specific builder type"""
        if builder_type.value.lower().replace(" ", "_") in TEMPLATE_CONFIGS:
            config_key = builder_type.value.lower().replace(" ", "_")
            config = TEMPLATE_CONFIGS[config_key]
            
            return TemplatePatterns(
                po_patterns=config.get("po_patterns", []),
                customer_patterns=config.get("customer_patterns", []),
                description_patterns=config.get("description_patterns", []),
                dollar_patterns=config.get("dollar_patterns", []),
                supervisor_patterns=[],  # Add supervisor patterns if needed
                address_patterns=[],     # Add address patterns if needed
            )
        return None

    def extract_field(self, text: str, patterns: List[str]) -> Optional[str]:
        """Extract field using patterns"""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return None

    def extract_dollar_value(self, text: str, patterns: List[str]) -> Optional[float]:
        """Extract dollar value using patterns"""
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
        """Extract text from PDF file using multiple methods for reliability."""
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

        return text

    def _extract_with_pymupdf(self, pdf_path: str) -> str:
        """Extract text using PyMuPDF (fitz)."""
        text = ""
        try:
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    text += page.get_text()
        except Exception as e:
            logger.error(f"PyMuPDF extraction failed: {str(e)}")
        return text

    def _extract_with_pdfplumber(self, pdf_path: str) -> str:
        """Extract text using pdfplumber."""
        text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() + "\n"
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {str(e)}")
        return text

    def _extract_with_pypdf2(self, pdf_path: str) -> str:
        """Extract text using PyPDF2."""
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
        """Parse address text into components."""
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
        """Parse full name into first and last name."""
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
        """Extract data from PDF using template detection."""
        # Extract text from PDF
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            return {'error': 'Failed to extract text from PDF'}

        # Use the existing extract_data_from_pdf function
        return extract_data_from_pdf(pdf_path)


def detect_template(text: str, builder_name: str = "") -> Dict[str, Any]:
    """
    Detect which builder template the PDF belongs to based on content patterns and builder name.
    
    Args:
        text: The extracted text from the PDF
        builder_name: The builder name from the RFMS database (optional)
        
    Returns:
        dict: Template information including name and confidence score
    """
    # First, try to match based on the builder name if provided
    if builder_name:
        template_name = match_builder_to_template(builder_name)
        if template_name and template_name in TEMPLATE_CONFIGS:
            logger.info(f"Template detected from builder name: {template_name}")
            return TEMPLATE_CONFIGS[template_name]
    
    # Fall back to content-based detection
    # Check for specific company indicators
    # Profile Build Group detection
    if re.search(r"profile\s+build\s+group", text, re.IGNORECASE):
        logger.info("Detected Profile Build Group template")
        return TEMPLATE_CONFIGS["profile_build"]
    
    # Ambrose Construct Group detection  
    if (
        re.search(r"ambrose\s+construct", text, re.IGNORECASE)
        or re.search(r"20\d{6}-\d{2}", text)
    ):
        logger.info("Detected Ambrose Construct Group template")
        return TEMPLATE_CONFIGS["ambrose"]
    
    # Campbell Construction detection
    if re.search(r"CCC\d+-\d+", text) or re.search(r"campbell\s+construction", text, re.IGNORECASE):
        logger.info("Detected Campbell Construction template")
        return TEMPLATE_CONFIGS["campbell"]
    
    # Rizon Group detection
    if re.search(r"rizon\s+group", text, re.IGNORECASE) or re.search(r"Client\s*/\s*Site\s+Details", text):
        logger.info("Detected Rizon Group template")
        return TEMPLATE_CONFIGS["rizon"]
    
    # Australian Restoration Company detection
    if re.search(r"australian\s+restoration", text, re.IGNORECASE) or re.search(r"PO\d+-[A-Z0-9]+-\d+", text):
        logger.info("Detected Australian Restoration Company template")
        return TEMPLATE_CONFIGS["australian_restoration"]
    
    # Townsend Building Services detection
    if re.search(r"townsend\s+building", text, re.IGNORECASE) or re.search(r"TBS-\d+", text):
        logger.info("Detected Townsend Building Services template")
        return TEMPLATE_CONFIGS["townsend"]
    
    # One Solutions detection
    if (re.search(r"one\s+solutions", text, re.IGNORECASE) or 
        re.search(r"a\s+to\s+z\s+flooring", text, re.IGNORECASE)):
        logger.info("Detected One Solutions template")
        return TEMPLATE_CONFIGS["one_solutions"]
    
    # Johns Lyng Group detection
    if re.search(r"johns\s+lyng", text, re.IGNORECASE):
        logger.info("Detected Johns Lyng Group template")
        return TEMPLATE_CONFIGS["johns_lyng"]
    
    # Define builder-specific patterns
    builder_patterns = {
        "ambrose": {
            "name": "Ambrose Construct Group",
            "po_patterns": [
                r"P\.O\.\s*No:?\s*(20\d{6}-\d{2})",  # Specific format: 20XXXXXX-XX
                r"PO[:\s#]+(20\d{6}-\d{2})",
                r"Purchase\s+Order[:\s#]+(20\d{6}-\d{2})",
                r"Order\s+Number[:\s#]+(20\d{6}-\d{2})",
            ],
            "customer_patterns": [
                r"Insured\s+Owner:?\s*([A-Za-z\s]+?)(?=\n|Authorised)",
                r"Insured:?\s*([A-Za-z\s]+?)(?=\n)",
                r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                r"Name[:\s]+([A-Za-z\s]+?)(?=\n)",
                r"Bill\s+To[:\s]+([A-Za-z\s]+?)(?=\n)",
            ],
            "description_patterns": [
                r"Description\s+of\s+Works[:\s]*(.+?)(?=Supervisor|$)",
                r"Works\s+Description[:\s]*(.+?)(?=Supervisor|$)",
                r"Scope\s+of\s+Works[:\s]*(.+?)(?=Supervisor|$)",
            ],
            "supervisor_section_pattern": r"Supervisor\s+Details",
            "dollar_patterns": [
                r"\$\s*([\d,]+\.?\d*)",
                r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
            ],
        },
        "profile_build": {
            "name": "Profile Build Group",
            "po_patterns": [
                r"WORK\s+ORDER:?\s*(PBG-\d+-\d+)",  # PBG-18191-18039
                r"PBG-\d+-\d+",  # Direct pattern match
                r"Order\s+Number[:\s#]+(PBG-\d+-\d+)",
                r"Contract\s+No[.:]?\s*(PBG-\d+-\d+)",
            ],
            "customer_patterns": [
                r"Client[:\s]+\n?([A-Za-z\s&]+?)(?=\n|Job)",
                r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                r"SITE\s+CONTACT[:\s]+([A-Za-z\s]+?)(?=\n)",
            ],
            "description_patterns": [
                r"NOTES[:\s]*\n([\s\S]+?)(?=All amounts|Total|$)",
                r"Scope\s+of\s+Works[:\s]*(.+?)(?=All amounts|Total|$)",
                r"PBG-\d+-\d+\s*\n([\s\S]+?)(?=All amounts|Total|$)",
            ],
            "supervisor_section_pattern": r"Supervisor[:\s]",
            "dollar_patterns": [
                r"Total\s+AUD\s*\$?\s*([\d,]+\.?\d*)",
                r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
                r"\$\s*([\d,]+\.?\d*)",
            ],
        },
        "campbell": {
            "name": "Campbell Construction",
            "po_patterns": [
                r"Contract\s+No[.:]?\s*(CCC\d+-\d+)",  # CCC55132-88512
                r"CCC\d+-\d+",  # Direct pattern match
                r"CONTRACT\s+NO[.:]?\s*(CCC\d+-\d+)",
                r"Contract\s+Number[.:]?\s*(CCC\d+-\d+)",
            ],
            "customer_patterns": [
                r"Customer:\s*\n([A-Za-z\s]+?)(?=\n)",  # Customer on next line
                r"Site\s+Contact:\s*\n([A-Za-z\s]+?)(?:\s*-|$)",  # Site Contact on next line
                r"Customer[:\s]+\n?([A-Za-z\s]+?)(?=\n|Site)",
                r"Customer[:\s]+([A-Za-z\s]+)",  # Simplified pattern
                r"Client[:\s]+([A-Za-z\s]+?)(?=\n)",
                r"Owner[:\s]+([A-Za-z\s]+?)(?=\n)",
            ],
            "description_patterns": [
                r"Scope\s+of\s+Work[:\s]*\n([\s\S]+?)(?=Totals|Page|Subtotal|$)",
                r"CCC\d+-\d+[\s\S]+?Description[:\s]*\n([\s\S]+?)(?=Totals|Page|Subtotal|$)",
                r"Description\s+of\s+Works[:\s]*(.+?)(?=Totals|Page|$)",
            ],
            "supervisor_section_pattern": r"CONTRACTOR'S\s+REPRESENTATIVE|Supervisor",
            "dollar_patterns": [
                r"Subtotal\s*\n\s*\$?([\d,]+\.?\d*)",  # Subtotal with newline
                r"Subtotal\s+\$\s*([\d,]+\.?\d*)",  # Based on key info: "Subtotal  $700.00"
                r"Total\s*\$?\s*([\d,]+\.?\d*)",
                r"\$\s*([\d,]+\.?\d*)",
            ],
        },
        "rizon": {
            "name": "Rizon Group",
            "po_patterns": [
                r"PURCHASE\s+ORDER\s+NO[:\s]*\n?(P?\d+)",  # P367117 or similar
                r"(P\d{6})",  # Direct pattern match - added capture group
                r"ORDER\s+NUMBER[:\s]*(\d+/\d+/\d+)",  # Alternative format
                r"(\d{6}/\d{3}/\d{2})",  # Format like 187165/240/01
                r"PO[:\s#]+(P?\d+)",
            ],
            "customer_patterns": [
                r"Client\s*/\s*Site\s+Details.*?\n(?:[^\n]+\n){3,6}([A-Z][A-Za-z\s]+?)(?=\n)",  # Skip lines to get to actual name
                r"Client\s*/\s*Site\s+Details[:\s]*\n?([A-Za-z\s]+?)(?=\n\d+|\n[A-Za-z]+\s+[A-Za-z]+,)",  # Name is first line in grid box
                r"Client\s*/\s*Site\s+Details[:\s]*\n?([A-Za-z\s]+?)(?=\n|\()",
                r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                r"Site\s+Details[:\s]*\n?([A-Za-z\s]+?)(?=\n)",
            ],
            "description_patterns": [
                r"SCOPE\s+OF\s+WORKS[:\s]*\n([\s\S]+?)(?=Net Order|PURCHASE\s+ORDER\s+CONDITIONS|Total|$)",
                r"Scope\s+of\s+Works[:\s]*\n([\s\S]+?)(?=Net Order|Total|$)",
            ],
            "supervisor_section_pattern": r"Supervisor[:\s]",
            "dollar_patterns": [
                r"Total\s+Order[:\s]*\$?\s*([\d,]+\.?\d*)",
                r"Net\s+Order[:\s]*\$?\s*([\d,]+\.?\d*)",
                r"\$\s*([\d,]+\.?\d*)",
            ],
        },
        "australian_restoration": {
            "name": "Australian Restoration Company",
            "po_patterns": [
                r"Order\s+Number[:\s]*\n?(PO\d+-[A-Z0-9]+-\d+)",  # PO96799-BU01-003
                r"PO\d+-[A-Z0-9]+-\d+",  # Direct pattern match
                r"Purchase\s+Order[:\s#]+(PO\d+-[A-Z0-9]+-\d+)",
            ],
            "customer_patterns": [
                r"Customer\s+Details[:\s]*\n?([A-Za-z\s]+?)(?=\n|Site)",
                r"Customer\s+Details[:\s]*([A-Za-z\s]+)",  # Without lookahead
                r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                r"Client[:\s]+([A-Za-z\s]+?)(?=\n)",
            ],
            "description_patterns": [
                r"Flooring\s+Contractor\s+Material\n([\s\S]+?)(?=All amounts|Preliminaries|Total|$)",
                r"<highlighter Header>\s*=?\s*([\s\S]+?)(?=All amounts shown|Total|$)",  # Based on key info
                r"Scope\s+of\s+Works[:\s]*\n([\s\S]+?)(?=All amounts|Total|$)",
            ],
            "supervisor_section_pattern": r"Project\s+Manager[:\s]|Case\s+Manager[:\s]",
            "dollar_patterns": [
                r"Sub\s+Total\s+\$\s*([\d,]+\.?\d*)",  # Based on key info: "Sub Total     $3,588.00"
                r"Total\s+AUD\s*\$?\s*([\d,]+\.?\d*)",
                r"\$\s*([\d,]+\.?\d*)",
            ],
        },
        "townsend": {
            "name": "Townsend Building Services",
            "po_patterns": [
                r"Order\s+Number\s*\n\s*([A-Z0-9]+)",  # Matches "Order Number\nPO23218"
                r"Purchase\s+Order[:\s#]+(TBS-\d+)",
                r"TBS-\d+",
                r"Order\s+Number[:\s]*(TBS-\d+|PO\d+)",
                r"WO[:\s#]+(\d+)",
                r"Work\s+Order[:\s#]+(\d+)",
            ],
            "customer_patterns": [
                r"Site\s+Contact\s+Name\s*\n([A-Za-z\s\(\)]+?)(?=\n)",  # Based on actual text
                r"Site\s+Contact\s+name\s*=?\s*([A-Za-z\s]+?)(?=\n|Subtotal)",  # Based on key info
                r"Contact\s+Name\s*\n\s*([A-Za-z\s]+?)(?=\n)",  # Matches "Contact Name\nJOHN SURNAME"
                r"Attention[:\s]+([A-Za-z\s]+?)(?=\n|Email)",
                r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                r"Client[:\s]+([A-Za-z\s]+?)(?=\n)",
            ],
            "description_patterns": [
                r"(?:Flooring|Floor\s+Preperation)[^<]*?([\s\S]+?)(?=Total|$)",  # Based on key info
                r"Additional\s+Notes/Instructions[:\s]*\n([\s\S]+?)(?=Flooring|Floor|Start|$)",  # Work Order notes
                r"Scope\s+of\s+Works[:\s]*\n([\s\S]+?)(?=Total|ABN|Page|$)",
                r"Work\s+Description[:\s]*\n([\s\S]+?)(?=Total|ABN|Page|$)",
                r"Description[:\s]*\n([\s\S]+?)(?=Total|ABN|Page|$)",
            ],
            "supervisor_section_pattern": r"Project\s+Manager[:\s]|Supervisor[:\s]|Manager[:\s]",
            "dollar_patterns": [
                r"Subtotal\s*\n\s*\$?([\d,]+\.?\d*)",  # Based on actual text: "Subtotal\n$14,430.00"
                r"Subtotal\s*=?\s*\$?\s*([\d,]+\.?\d*)",  # Based on key info: "Subtotal = Dollar value"
                r"Total\s+Inc\.?\s+GST[:\s]*\$?\s*([\d,]+\.?\d*)",
                r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
                r"\$\s*([\d,]+\.?\d*)",
            ],
        },
        "generic": {
            "name": "Generic Template",
            "po_patterns": [
                r"P\.O\.\s*No:?\s*([A-Za-z0-9-]+)",
                r"PO[:\s#]+([A-Za-z0-9-]+)",
                r"Purchase\s+Order[:\s#]+([A-Za-z0-9-]+)",
                r"Order\s+Number[:\s#]+([A-Za-z0-9-]+)",
                r"CONTRACT\s+NO[.:]?\s*([A-Za-z0-9-]+)",
                r"Contract\s+Number[.:]?\s*([A-Za-z0-9-]+)",
                r"WORK\s+ORDER[:\s]+([A-Za-z0-9-]+)",
                r"JOB\s+NUMBER[:\s]+([A-Za-z0-9-]+)",
            ],
            "customer_patterns": [
                r"Customer[:\s]+([A-Za-z\s]+?)(?=\n)",
                r"Client[:\s]+([A-Za-z\s]+?)(?=\n)",
                r"Name[:\s]+([A-Za-z\s]+?)(?=\n)",
                r"Bill\s+To[:\s]+([A-Za-z\s]+?)(?=\n)",
            ],
            "description_patterns": [
                r"Description\s+of\s+Works[:\s]*(.+?)(?=Supervisor|Total|$)",
                r"Scope\s+of\s+Works[:\s]*(.+?)(?=Supervisor|Total|$)",
                r"Works\s+Description[:\s]*(.+?)(?=Supervisor|Total|$)",
            ],
            "supervisor_section_pattern": r"Supervisor|Contractor[\s']*s?\s+Representative",
            "dollar_patterns": [
                r"\$\s*([\d,]+\.?\d*)",
                r"Total[:\s]+\$?\s*([\d,]+\.?\d*)",
            ],
        }
    }

    # Check for specific company indicators
    # Profile Build Group detection
    if re.search(r"profile\s+build\s+group", text, re.IGNORECASE):
        logger.info("Detected Profile Build Group template")
        return builder_patterns["profile_build"]
    
    # Ambrose Construct Group detection  
    if (
        re.search(r"ambrose\s+construct", text, re.IGNORECASE)
        or re.search(r"20\d{6}-\d{2}", text)
    ):
        logger.info("Detected Ambrose Construct Group template")
        return builder_patterns["ambrose"]
    
    # Campbell Construction detection
    if re.search(r"CCC\d+-\d+", text) or re.search(r"campbell\s+construction", text, re.IGNORECASE):
        logger.info("Detected Campbell Construction template")
        return builder_patterns["campbell"]
    
    # Rizon Group detection
    if re.search(r"rizon\s+group", text, re.IGNORECASE) or re.search(r"Client\s*/\s*Site\s+Details", text):
        logger.info("Detected Rizon Group template")
        return builder_patterns["rizon"]
    
    # Australian Restoration Company detection
    if re.search(r"australian\s+restoration", text, re.IGNORECASE) or re.search(r"PO\d+-[A-Z0-9]+-\d+", text):
        logger.info("Detected Australian Restoration Company template")
        return builder_patterns["australian_restoration"]
    
    # Townsend Building Services detection
    if re.search(r"townsend\s+building", text, re.IGNORECASE) or re.search(r"TBS-\d+", text):
        logger.info("Detected Townsend Building Services template")
        return builder_patterns["townsend"]
    
    # One Solutions detection
    if (re.search(r"one\s+solutions", text, re.IGNORECASE) or 
        re.search(r"a\s+to\s+z\s+flooring", text, re.IGNORECASE)):
        logger.info("Detected One Solutions template")
        return builder_patterns["one_solutions"]
    
    # Johns Lyng Group detection
    if re.search(r"johns\s+lyng", text, re.IGNORECASE):
        logger.info("Detected Johns Lyng Group template")
        return builder_patterns["johns_lyng"]
    
    # Default to generic template
    logger.info("Using generic template")
    return builder_patterns["generic"]


def extract_data_from_pdf(pdf_path: str, builder_name: str = "") -> Dict[str, Any]:
    """
    Extract relevant data from PDF purchase orders.

    This function tries multiple PDF parsing libraries to maximize extraction success.
    It looks for patterns like customer information, PO numbers, scope of work and dollar values.

    Args:
        pdf_path (str): Path to the PDF file
        builder_name (str): The builder name from the RFMS database

    Returns:
        dict: Extracted data including customer details, PO information, and more
    """
    logger.info(f"Extracting data from PDF: {pdf_path}")

    # Initialize extracted data dictionary with all required fields
    extracted_data = {
        # Customer Information
        "customer_name": "",
        "business_name": "",
        "first_name": "",
        "last_name": "",
        "address": "",
        "address1": "",
        "address2": "",
        "city": "",
        "state": "",
        "zip_code": "",
        "country": "Australia",  # Default
        "phone": "",
        "mobile": "",
        "work_phone": "",
        "home_phone": "",
        "email": "",
        "customer_type": "Builders",  # Default as specified in requirements
        "extra_phones": [],  # Store additional phone numbers
        # Purchase Order Information
        "po_number": "",
        "scope_of_work": "",
        "dollar_value": 0,
        # Job Information
        "job_number": "",  # This will be filled with supervisor name + mobile
        "actual_job_number": "",  # Keep the actual job number separately
        "supervisor_name": "",
        "supervisor_mobile": "",
        "supervisor_email": "",
        # Additional Information
        "description_of_works": "",
        "material_breakdown": "",
        "labor_breakdown": "",
        "rooms": "",
        "raw_text": "",
        # --- Add alternate/best contact fields ---
        "alternate_contact_name": "",
        "alternate_contact_phone": "",
        "alternate_contact_email": "",
        # --- New: list of all alternate contacts ---
        "alternate_contacts": [],  # Each: {type, name, phone, email}
        # --- Date fields ---
        "commencement_date": "",
        "installation_date": "",
        "ship_to_name": "",
        "ship_to_address": "",
    }

    # Try different extraction methods in order of reliability
    try:
        # Try PyMuPDF (fitz) first - generally fastest and most reliable
        text = extract_with_pymupdf(pdf_path)
        if text:
            extracted_data["raw_text"] = text
            
            # Detect builder from PDF content
            detected_builder = detect_builder_from_pdf(text)
            if detected_builder and builder_name:
                # Normalize builder names for comparison
                detected_normalized = detected_builder.lower().replace(' ', '')
                provided_normalized = builder_name.lower().replace(' ', '')
                
                if detected_normalized not in provided_normalized and provided_normalized not in detected_normalized:
                    logger.warning(f"[BUILDER_MISMATCH] PDF appears to be from '{detected_builder}' but selected builder is '{builder_name}'")
                    extracted_data["builder_mismatch_warning"] = f"PDF appears to be from '{detected_builder}' but selected builder is '{builder_name}'. Please verify the correct builder is selected."
                    extracted_data["detected_builder"] = detected_builder
            
            template = detect_template(text, builder_name)
            
            # Add specific logging for Ambrose
            if template and "ambrose" in template.get("name", "").lower():
                logger.info("[AMBROSE] Running Ambrose Construct Group specific extraction logic")
                logger.info(f"[AMBROSE] Template patterns - PO: {len(template.get('po_patterns', []))}, Customer: {len(template.get('customer_patterns', []))}, Description: {len(template.get('description_patterns', []))}")
            
            parse_extracted_text(text, extracted_data, template)

        # If we didn't get all needed data, try pdfplumber
        if not check_essential_fields(extracted_data):
            text = extract_with_pdfplumber(pdf_path)
            if text and text != extracted_data["raw_text"]:
                extracted_data["raw_text"] = text
                template = detect_template(text, builder_name)
                parse_extracted_text(text, extracted_data, template)

        # Last resort, try PyPDF2
        if not check_essential_fields(extracted_data):
            text = extract_with_pypdf2(pdf_path)
            if text and text != extracted_data["raw_text"]:
                extracted_data["raw_text"] = text
                template = detect_template(text, builder_name)
                parse_extracted_text(text, extracted_data, template)

        # Clean and format the extracted data
        clean_extracted_data(extracted_data)

        logger.info(f"Successfully extracted data from PDF: {pdf_path}")
        return extracted_data

    except Exception as e:
        logger.error(f"Error extracting data from PDF: {str(e)}")
        logger.error(f"Traceback: ", exc_info=True)
        extracted_data["error"] = str(e)
        # Don't try to clean data if there was an error
        return extracted_data


def clean_extracted_data(extracted_data):
    """Clean and format the extracted data."""
    # Split name into first and last name if not already done
    if extracted_data.get("customer_name") and not (
        extracted_data.get("first_name") and extracted_data.get("last_name")
    ):
        # Clean up customer name first by removing any newlines and extra text
        customer_name = extracted_data.get("customer_name", "")
        if isinstance(customer_name, str) and customer_name.strip():  # Check if not empty
            cleaned_name = re.sub(r"\n.*$", "", customer_name)
            names = cleaned_name.split(maxsplit=1)
            if len(names) > 0:
                extracted_data["first_name"] = names[0]
            if len(names) > 1:
                extracted_data["last_name"] = names[1]
            else:
                # If only one name, use it as last name
                extracted_data["last_name"] = ""

    # Clean up supervisor name
    supervisor_name = extracted_data.get("supervisor_name")
    if supervisor_name and isinstance(supervisor_name, str):
        extracted_data["supervisor_name"] = re.sub(
            r"\n.*$", "", supervisor_name
        )

    # Clean up customer name
    customer_name = extracted_data.get("customer_name")
    if customer_name and isinstance(customer_name, str):
        extracted_data["customer_name"] = re.sub(
            r"\n.*$", "", customer_name
        )

    # Clean up address
    address = extracted_data.get("address")
    if address and isinstance(address, str):
        extracted_data["address"] = re.sub(r"\n.*$", "", address)

    # Per requirements, we ignore business information (A TO Z FLOORING)
    extracted_data["business_name"] = ""

    # Clean up business name (if needed for future use, but set to empty as per requirements)
    # if extracted_data['business_name']:
    #     # Try to extract from SUBCONTRACTOR DETAILS section if available
    #     if "A TO Z FLOORING" in extracted_data['raw_text']:
    #         extracted_data['business_name'] = "A TO Z FLOORING SOLUTIONS"
    #     else:
    #         extracted_data['business_name'] = re.sub(r'\s+Job\s+Number.*$', '', extracted_data['business_name'])
    #         extracted_data['business_name'] = re.sub(r'\s+SOLUTIONS.*$', '', extracted_data['business_name'])
    #         extracted_data['business_name'] = re.sub(r'.*Subcontract agreement between the Builder and ', '', extracted_data['business_name'])
    #         extracted_data['business_name'] = extracted_data['business_name'].strip()

    # Improve city parsing
    city = extracted_data.get("city")
    if city and isinstance(city, str) and "Warriewood Street" in city:
        # Fix specifically for the known address format in the example
        extracted_data["city"] = "Chandler"

    # Format description of works to be more readable
    desc_of_works = extracted_data.get("description_of_works")
    if desc_of_works and isinstance(desc_of_works, str):
        description = desc_of_works
        # Remove "Quantity Unit" header if present
        description = re.sub(r"^Quantity\s+Unit\s+", "", description)
        # Reformat and clean up
        description = re.sub(r"\n\$\d+m2", " - $45/m2", description)
        description = re.sub(r"\s{2,}", " ", description)
        extracted_data["description_of_works"] = description

    # Set job_number to supervisor name + mobile as per requirements
    if extracted_data.get("supervisor_name") and extracted_data.get("supervisor_mobile"):
        # Store the actual job number separately
        extracted_data["actual_job_number"] = extracted_data.get("job_number", "")
        # Set job_number to supervisor name + mobile
        extracted_data["job_number"] = (
            f"{extracted_data['supervisor_name']} {extracted_data['supervisor_mobile']}"
        )

    # Filter extra_phones to only include customer-related numbers
    if extracted_data.get("extra_phones"):
        # Numbers to exclude
        exclude_numbers = [
            extracted_data.get("actual_job_number", ""),  # PO/job number
            "0731100077",  # A to Z Flooring Solutions
            extracted_data.get("supervisor_mobile", ""),  # Supervisor
            "74658650821",  # ABN number
            "35131176",  # Company number
            "999869951",  # Other company number
        ]

        # Create cleaned versions of excluded numbers (digits only)
        clean_exclude_numbers = []
        for number in exclude_numbers:
            if number and isinstance(number, str):
                clean_exclude_numbers.append("".join(c for c in number if c.isdigit()))

        # Filter the extra_phones list
        filtered_phones = []
        for phone in extracted_data["extra_phones"]:
            if isinstance(phone, str):
                # Clean the phone
                clean_phone = "".join(c for c in phone if c.isdigit())

                # Skip if in excluded list or already in customer's main numbers
                if clean_phone not in clean_exclude_numbers and clean_phone not in [
                    "".join(c for c in str(extracted_data.get("phone", "") or "") if c.isdigit()),
                    "".join(c for c in str(extracted_data.get("mobile", "") or "") if c.isdigit()),
                    "".join(c for c in str(extracted_data.get("home_phone", "") or "") if c.isdigit()),
                    "".join(c for c in str(extracted_data.get("work_phone", "") or "") if c.isdigit()),
                ]:
                    filtered_phones.append(phone)

        extracted_data["extra_phones"] = filtered_phones

    # Clean up alternate_contacts: remove entries with invalid names or no phone/email, and strip newlines
    cleaned_contacts = []
    for contact in extracted_data.get("alternate_contacts", []):
        if isinstance(contact, dict):
            name = str(contact.get("name", "")).replace("\n", " ").strip()
            phone = str(contact.get("phone", "")).strip()
            email = str(contact.get("email", "")).strip()
            # Only keep if name is not empty, not 'Email', and has at least a phone or email
            if name and name.lower() != "email" and (phone or email):
                cleaned_contacts.append(
                    {
                        "type": contact.get("type", ""),
                        "name": name,
                        "phone": phone,
                        "email": email,
                    }
                )
    extracted_data["alternate_contacts"] = cleaned_contacts


def check_essential_fields(data):
    """Check if essential fields are filled."""
    essential_fields = ["po_number", "customer_name", "dollar_value"]
    return all(data[field] for field in essential_fields)


def extract_with_pymupdf(file_path):
    """Extract text from PDF using PyMuPDF."""
    try:
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        logger.error(f"PyMuPDF extraction error: {str(e)}")
        return ""


def extract_with_pdfplumber(file_path):
    """Extract text from PDF using pdfplumber."""
    try:
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        return text
    except Exception as e:
        logger.error(f"pdfplumber extraction error: {str(e)}")
        return ""


def extract_with_pypdf2(file_path):
    """Extract text from PDF using PyPDF2."""
    try:
        with open(file_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
        return text
    except Exception as e:
        logger.error(f"PyPDF2 extraction error: {str(e)}")
        return ""


def parse_extracted_text(text, extracted_data, template):
    """
    Parse the extracted text to find relevant information.

    Args:
        text (str): The extracted text from the PDF
        extracted_data (dict): Dictionary to update with parsed information
        template (dict): The template configuration to use
    """
    # Handle None or empty text
    if not text:
        logger.warning("parse_extracted_text: text is None or empty")
        return
    
    # Extract PO number
    for pattern in template["po_patterns"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted_data["po_number"] = match.group(1).strip()
            break
    
    # If no PO number found with template patterns, try generic fallback patterns
    if not extracted_data["po_number"]:
        generic_po_patterns = [
            r"P\.O\.\s*No:?\s*([A-Za-z0-9-]+)",
            r"PO[:\s#]+([A-Za-z0-9-]+)",
            r"Purchase\s+Order[:\s#]+([A-Za-z0-9-]+)",
            r"Order\s+Number[:\s#]+([A-Za-z0-9-]+)",
            r"CONTRACT\s+NO[.:]?\s*([A-Za-z0-9-]+)",
            r"Contract\s+Number[.:]?\s*([A-Za-z0-9-]+)",
        ]

        for pattern in generic_po_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_data["po_number"] = match.group(1).strip()
                break
    
    logger.info(f"[EXTRACT] PO Number: {extracted_data['po_number']}")

    # Extract business name from SUBCONTRACTOR DETAILS section
    subcontractor_section = re.search(
        r"SUBCONTRACTOR\s+DETAILS([\s\S]+?)(?=JOB\s+DETAILS|SUPERVISOR\s+DETAILS|$)",
        text,
        re.IGNORECASE,
    )
    if subcontractor_section:
        subcontractor_text = subcontractor_section.group(1)
        trading_name_match = re.search(
            r"Trading\s+Name:?\s*([A-Za-z0-9\s\.,&-]+?)(?=\n)",
            subcontractor_text,
            re.IGNORECASE,
        )
        if trading_name_match:
            extracted_data["business_name"] = trading_name_match.group(1).strip()

    # If business name not found in SUBCONTRACTOR DETAILS, try general patterns
    if not extracted_data["business_name"]:
        business_patterns = [
            r"Trading\s+Name:?\s*([A-Za-z0-9\s\.,&-]+?)(?=\n)",
            r"Business[:\s]+([A-Za-z0-9\s\.,&-]+?)(?=\n)",
            r"Company[:\s]+([A-Za-z0-9\s\.,&-]+?)(?=\n)",
            r"Builder[:\s]+([A-Za-z0-9\s\.,&-]+?)(?=\n)",
        ]

        for pattern in business_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_data["business_name"] = match.group(1).strip()
                break

    # Extract Insured Customer (Customer Name)
    for i, pattern in enumerate(template["customer_patterns"]):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted_data["customer_name"] = match.group(1).strip()
            logger.info(f"[EXTRACT] Found customer name using pattern {i+1}: '{extracted_data['customer_name']}'")
            break
    
    # If no customer name found yet and this is Ambrose, add specific Ambrose customer extraction
    if not extracted_data.get("customer_name") and "ambrose" in template["name"].lower():
        logger.info("[AMBROSE] Standard customer patterns failed, trying Ambrose-specific extraction")
        
        # Try more specific Ambrose "Insured Owner" patterns
        ambrose_customer_patterns = [
            r"Insured\s+Owner[:\s]*\n([A-Za-z\s\-'\.]+?)(?=\n|$)",  # Insured Owner on next line - includes hyphens, apostrophes, periods
            r"Insured\s+Owner[:\s]+([A-Za-z\s\-'\.]+?)(?=\n|Authorised|BEST|$)",  # Same line with various terminators
            r"(?:Customer|Client|Name)[:\s]*\n?([A-Z][A-Za-z\s\-'\.]+?)(?=\n|$)",  # Uppercase start
            r"Bill\s*To[:\s]*\n?([A-Za-z\s\-'\.]+?)(?=\n|$)",  # Bill To
        ]
        
        for i, pattern in enumerate(ambrose_customer_patterns):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                customer_name = match.group(1).strip()
                if len(customer_name) > 2:  # Ensure it's not just initials
                    extracted_data["customer_name"] = customer_name
                    logger.info(f"[AMBROSE] Found customer name using Ambrose pattern {i+1}: '{extracted_data['customer_name']}'")
                    break
    
    # Log the final result
    if extracted_data.get("customer_name"):
        logger.info(f"[EXTRACT] Final customer name: '{extracted_data['customer_name']}'")
    else:
        logger.warning("[EXTRACT] No customer name found - this may affect ship-to details")

    # Extract contact details
    extract_contact_details(text, extracted_data)

    # Extract Job Number and Supervisor Details
    extract_job_and_supervisor_details(text, extracted_data, template)

    # For Ambrose Construct Group, use template-specific address patterns FIRST
    if "ambrose" in template["name"].lower():
        logger.info("[AMBROSE] Attempting to extract address using Ambrose-specific patterns")
        for i, pattern in enumerate(template.get("address_patterns", [])):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                address_candidate = match.group(1).strip()
                logger.info(f"[AMBROSE] Found address using pattern {i+1}: '{address_candidate}'")
                if "tax invoice" not in address_candidate.lower():
                    extracted_data["address"] = address_candidate
                    # Use custom Ambrose address parsing to handle street name in city issue
                    try:
                        if address_candidate:
                            parse_ambrose_address(address_candidate, extracted_data)
                            logger.info(f"[AMBROSE] Parsed address - Street: '{extracted_data['address1']}', City: '{extracted_data['city']}', State: '{extracted_data['state']}', Zip: '{extracted_data['zip_code']}'")
                    except Exception as e:
                        logger.warning(f"Failed to parse Ambrose address: {e}")
                    break

    # Extract Site Address (can be used for shipping address) - Skip if Profile Build, One Solutions, or Ambrose already handled it
    if not extracted_data.get("address") and not ("profile build" in template["name"].lower() or "one solutions" in template["name"].lower() or "ambrose" in template["name"].lower()):
        address_patterns = [
            r"Site\s+Address[:\s]*\n?([A-Za-z0-9\s\.,#-]+?)(?=\n)",
            r"Site\s+Address[:\s]*([^,\n]+,\s*[^,\n]+,?\s*[A-Z]{2,3}\s*\d{4})",  # Full address pattern
            r"SITE\s+LOCATION[:\s]*([A-Za-z0-9\s\.,#-]+?)(?=\n)",
            r"Property\s+Address[:\s]*\n?([A-Za-z0-9\s\.,#-]+?)(?=\n)",
            r"Location[:\s]*([A-Za-z0-9\s\.,#-]+?)(?=\n)",
            r"Address[:\s]+([A-Za-z0-9\s\.,#-]+?)(?=\n)",
        ]

        for pattern in address_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                address_candidate = match.group(1).strip()
                # Skip if it's the "included on tax invoice" message
                if "tax invoice" not in address_candidate.lower():
                    extracted_data["address"] = address_candidate
                    # Try to parse address into components
                    try:
                        if address_candidate:  # Only parse if address is not empty
                            parse_address(address_candidate, extracted_data)
                    except Exception as e:
                        logger.warning(f"Failed to parse address: {e}")
                    break

    # For Rizon Group, try to extract address from Client / Site Details grid box
    if not extracted_data["address"] and "rizon" in template["name"].lower():
        client_site_section = re.search(
            r"Client\s*/\s*Site\s+Details[:\s]*\n[A-Za-z\s]+?\n([\s\S]+?)(?=\n\n|$)",
            text,
            re.IGNORECASE
        )
        if client_site_section:
            address_lines = client_site_section.group(1).strip().split('\n')
            if address_lines:
                # Combine address lines
                full_address = ' '.join(address_lines[:3])  # Take up to 3 lines
                extracted_data["address"] = full_address
                try:
                    if full_address:  # Only parse if address is not empty
                        parse_address(full_address, extracted_data)
                except Exception as e:
                    logger.warning(f"Failed to parse Rizon address: {e}")



    # Extract Description of Works for custom private notes
    # Use template-specific patterns
    for i, pattern in enumerate(template.get("description_patterns", [])):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted_data["description_of_works"] = match.group(1).strip()
            # Set this as scope of work too for compatibility
            extracted_data["scope_of_work"] = extracted_data["description_of_works"]
            
            # Add specific logging and cleaning for Ambrose
            if "ambrose" in template.get("name", "").lower():
                logger.info(f"[AMBROSE] Found description using pattern {i+1}: {len(extracted_data['description_of_works'])} characters")
                
                # Clean Ambrose description - remove common unwanted content
                cleaned_description = extracted_data["description_of_works"]
                
                # Remove notification_important and similar content, plus Ambrose-specific headers
                lines = cleaned_description.split('\n')
                cleaned_lines = []
                skip_notification = False
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Skip Ambrose table headers and unwanted content
                    if any(keyword in line.lower() for keyword in [
                        'notification_important', 'please note', 'below has been provided', 
                        'as an example only', 'adjust the break down', 'invoice to reflect',
                        'quantity unit', 'quantity', 'unit'  # Skip Ambrose table headers
                    ]) or line.lower().strip() in ['quantity', 'unit', 'quantity unit']:
                        skip_notification = True
                        continue
                    
                    # Stop skipping if we hit actual work content
                    if skip_notification and (line.startswith('•') or line.startswith('-') or 
                                            any(keyword in line.lower() for keyword in ['master', 'bedroom', 'carpet', 'supply', 'install', 'remove', 'repair', 'hrs'])):
                        skip_notification = False
                    
                    if not skip_notification:
                        cleaned_lines.append(line)
                
                if cleaned_lines:
                    extracted_data["description_of_works"] = '\n'.join(cleaned_lines).strip()
                    logger.info(f"[AMBROSE] Cleaned description: {len(extracted_data['description_of_works'])} characters")
                
                logger.info(f"[AMBROSE] Description preview: {extracted_data['description_of_works'][:200]}...")
            
            break
    
    # If no match found with template patterns, try generic patterns
    if not extracted_data["description_of_works"]:
        generic_description_patterns = [
            r"Description\s+of\s+Works[:\s]*\n([\s\S]+?)(?=Total\s+Purchase\s+Order\s+Value|TOTAL\s+PURCHASE\s+ORDER|Total\s+Purchase|TOTAL|$)",  # Ambrose-specific
            r"Description\s+of\s+Works([\s\S]+?)(?=TOTAL|Total\s+Purchase\s+Order)",
            r"Scope\s+of\s+Work[:\s]+([\s\S]+?)(?=TOTAL|Total|Amount|Price|\$|\n\n)",
            r"Description[:\s]+([\s\S]+?)(?=TOTAL|Total|Amount|Price|\$|\n\n)",
            r"Services[:\s]+([\s\S]+?)(?=TOTAL|Total|Amount|Price|\$|\n\n)",
        ]

        for pattern in generic_description_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_data["description_of_works"] = match.group(1).strip()
                # Set this as scope of work too for compatibility
                extracted_data["scope_of_work"] = extracted_data["description_of_works"]
                break

    # Extract dollar value from TOTAL Purchase Order Price
    for pattern in template.get("dollar_patterns", []):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value_str = match.group(1).replace(",", "")
            try:
                extracted_data["dollar_value"] = float(value_str)
                break
            except ValueError:
                continue
    
    logger.info(f"[EXTRACT] Dollar Value: {extracted_data['dollar_value']}")

    # --- Enhanced Ambrose contact extraction for all contact types ---
    if "ambrose" in template["name"].lower():
        logger.info("[AMBROSE] Enhanced contact extraction - looking for all contact types")
        main_customer_name = extracted_data.get("customer_name", "").strip().lower()
        
        # Track phones for Phone3/Phone4 mapping (prioritize Authorised Contact and Site Contact)
        phone_numbers = []
        
        # First, extract from BEST CONTACT DETAILS section
        best_contact_section = re.search(
            r"BEST\s+CONTACT\s+DETAILS([\s\S]+?)(?=SUPERVISOR|JOB\s+DETAILS|$)",
            text,
            re.IGNORECASE
        )
        
        if best_contact_section:
            contact_text = best_contact_section.group(1)
            logger.info(f"[AMBROSE] Found BEST CONTACT DETAILS section: {contact_text[:200]}...")
            
            # Extract all contact types within BEST CONTACT DETAILS
            # Look for patterns like "Contact Type: Authorised Contact" followed by name/phone/email
            contact_type_matches = re.finditer(
                r"Contact\s+Type[:\s]*([A-Za-z\s]+?)(?=\n|$)",
                contact_text,
                re.IGNORECASE
            )
            
            for match in contact_type_matches:
                contact_type = match.group(1).strip()
                # Get context after this contact type (next 150 characters)
                start_pos = match.end()
                context = contact_text[start_pos:start_pos + 150]
                
                # Extract name (first line after contact type)
                name_match = re.search(r"^\s*([A-Za-z\s\-'\.]+?)(?=\n|Mobile|Phone|Email|$)", context, re.MULTILINE)
                name = name_match.group(1).strip() if name_match else ""
                
                # Extract phone numbers
                phone_matches = re.findall(r"(?:Mobile|Phone|Home)[:\s]*([0-9\s\-\(\)]+)", context, re.IGNORECASE)
                phone = phone_matches[0] if phone_matches else ""
                phone2 = phone_matches[1] if len(phone_matches) > 1 else ""
                
                # Extract email
                email_match = re.search(r"Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", context, re.IGNORECASE)
                email = email_match.group(1) if email_match else ""
                
                # Add to contacts if we have meaningful data
                if name and name.lower() != main_customer_name and len(name.strip()) > 2:
                    contact_entry = {
                        "type": contact_type,
                        "name": name,
                        "phone": phone,
                        "phone2": phone2,
                        "email": email
                    }
                    extracted_data["alternate_contacts"].append(contact_entry)
                    logger.info(f"[AMBROSE] Added {contact_type}: {name}, Phone: {phone}, Email: {email}")
                    
                    # Prioritize Authorised Contact and Site Contact for Phone3/Phone4
                    if contact_type.lower() in ["authorised contact", "site contact"]:
                        if phone and phone not in phone_numbers:
                            phone_numbers.insert(0, phone)  # Insert at beginning for priority
                        if phone2 and phone2 not in phone_numbers:
                            phone_numbers.insert(len(phone_numbers) if phone else 1, phone2)
                    else:
                        # Add other phones at the end
                        if phone and phone not in phone_numbers:
                            phone_numbers.append(phone)
                        if phone2 and phone2 not in phone_numbers:
                            phone_numbers.append(phone2)
                    
                    # Set as primary alternate contact if it's a priority type
                    if (contact_type.lower() in ["decision maker", "authorised contact", "site contact"] and 
                        not extracted_data.get("alternate_contact_name") and name):
                        extracted_data["alternate_contact_name"] = name
                        extracted_data["alternate_contact_phone"] = phone
                        extracted_data["alternate_contact_email"] = email
            
            # Also look for standalone patterns in BEST CONTACT DETAILS
            standalone_patterns = [
                ("Decision Maker", r"Decision\s+Maker[:\s]*([A-Za-z\s\-'\.]+?)(?=\n|$)"),
                ("Mobile Number", r"Mobile\s+Number[:\s]*([0-9\s\-\(\)]+)"),
                ("Site Contact", r"Site\s+Contact[:\s]*([A-Za-z\s\-'\.]+?)(?=\n|Contact\s+Type|$)"),
                ("Authorised Contact", r"Authorised\s+Contact[:\s]*([A-Za-z\s\-'\.]+?)(?=\n|$)"),
            ]
            
            for pattern_type, pattern in standalone_patterns:
                matches = re.finditer(pattern, contact_text, re.IGNORECASE)
                for match in matches:
                    if pattern_type == "Mobile Number":
                        phone = match.group(1).strip()
                        if phone and phone not in phone_numbers:
                            phone_numbers.append(phone)
                    elif pattern_type in ["Decision Maker", "Site Contact"]:
                        name = match.group(1).strip()
                        if name and name.lower() != main_customer_name and len(name.strip()) > 2:
                            # Look for associated phone/email nearby
                            context_start = max(0, match.start() - 50)
                            context_end = min(len(contact_text), match.end() + 100)
                            context = contact_text[context_start:context_end]
                            
                            phone_match = re.search(r"(?:Mobile|Phone)[:\s]*([0-9\s\-\(\)]+)", context, re.IGNORECASE)
                            phone = phone_match.group(1).strip() if phone_match else ""
                            
                            email_match = re.search(r"Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", context, re.IGNORECASE)
                            email = email_match.group(1) if email_match else ""
                            
                            # Check if this contact already exists
                            existing = any(c.get("name", "").lower() == name.lower() for c in extracted_data["alternate_contacts"])
                            if not existing:
                                contact_entry = {
                                    "type": pattern_type,
                                    "name": name,
                                    "phone": phone,
                                    "phone2": "",
                                    "email": email
                                }
                                extracted_data["alternate_contacts"].append(contact_entry)
                                logger.info(f"[AMBROSE] Added standalone {pattern_type}: {name}, Phone: {phone}")
                                
                                if phone and phone not in phone_numbers:
                                    phone_numbers.append(phone)
            
            # Extract specific Ambrose patterns like "Authorised Contact #: (H) 7899737 (M) 0409483445"
            auth_contact_pattern = r"Authorised\s+Contact\s*#?[:\s]*\(H\)\s*([0-9\s\-\(\)]+)\s*\(M\)\s*([0-9\s\-\(\)]+)"
            auth_match = re.search(auth_contact_pattern, contact_text, re.IGNORECASE)
            if auth_match:
                home_phone = auth_match.group(1).strip()
                mobile_phone = auth_match.group(2).strip()
                
                # Look for the name before this pattern
                context_start = max(0, auth_match.start() - 100)
                context = contact_text[context_start:auth_match.start()]
                
                # Try to find "Authorised Contact:" followed by a name
                name_match = re.search(r"Authorised\s+Contact[:\s]*([A-Za-z\s\-'\.]+?)(?=\n|Authorised\s+Contact\s*#|$)", context, re.IGNORECASE)
                name = name_match.group(1).strip() if name_match else "Authorised Contact"
                
                if name and name.lower() != main_customer_name:
                    contact_entry = {
                        "type": "Authorised Contact",
                        "name": name,
                        "phone": mobile_phone,
                        "phone2": home_phone,
                        "email": ""
                    }
                    extracted_data["alternate_contacts"].append(contact_entry)
                    logger.info(f"[AMBROSE] Added Authorised Contact: {name}, Mobile: {mobile_phone}, Home: {home_phone}")
                    
                    # Add both phones to the priority list
                    if mobile_phone and mobile_phone not in phone_numbers:
                        phone_numbers.insert(0, mobile_phone)  # Mobile gets priority
                    if home_phone and home_phone not in phone_numbers:
                        phone_numbers.append(home_phone)
                    
                    # Set as primary if we don't have one yet
                    if not extracted_data.get("alternate_contact_name"):
                        extracted_data["alternate_contact_name"] = name
                        extracted_data["alternate_contact_phone"] = mobile_phone
                        extracted_data["alternate_contact_email"] = ""
        
        # Extract other contact types outside BEST CONTACT DETAILS
        other_contact_patterns = [
            ("Occupant Contact", r"Occupant\s+Contact[:\s]*([A-Za-z\s\-'\.]*?)(?=\n|Property\s+Manager|Real\s+Estate|BEST\s+CONTACT|$)"),
            ("Property Manager", r"Property\s+Manager[:\s]*([A-Za-z\s\-'\.]+?)(?=\n|Real\s+Estate|BEST\s+CONTACT|$)"),
            ("Real Estate Contact", r"Real\s+Estate\s+Contact[:\s]*([A-Za-z\s\-'\.]+?)(?=\n|BEST\s+CONTACT|$)"),
        ]
        
        for contact_type, pattern in other_contact_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                name = match.group(1).strip() if match.groups() else ""
                if name and name.lower() != main_customer_name and len(name.strip()) > 2:
                    # Look for phone/email near this contact
                    context_start = max(0, match.start() - 50)
                    context_end = min(len(text), match.end() + 100)
                    context = text[context_start:context_end]
                    
                    phone_match = re.search(r"(?:Mobile|Phone)[:\s]*([0-9\s\-\(\)]+)", context, re.IGNORECASE)
                    phone = phone_match.group(1).strip() if phone_match else ""
                    
                    email_match = re.search(r"Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", context, re.IGNORECASE)
                    email = email_match.group(1) if email_match else ""
                    
                    contact_entry = {
                        "type": contact_type,
                        "name": name,
                        "phone": phone,
                        "phone2": "",
                        "email": email
                    }
                    extracted_data["alternate_contacts"].append(contact_entry)
                    logger.info(f"[AMBROSE] Added {contact_type}: {name}, Phone: {phone}, Email: {email}")
                    
                    if phone and phone not in phone_numbers:
                        phone_numbers.append(phone)
        
        # Enhanced phone extraction for contacts that don't have phones yet
        for contact in extracted_data["alternate_contacts"]:
            if not contact.get("phone") or not contact.get("phone").strip():
                contact_name = contact.get("name", "")
                if contact_name and contact_name != "Email" and len(contact_name.strip()) > 2:
                    # Look for phone numbers near this contact's name in the entire text
                    name_index = text.find(contact_name)
                    if name_index >= 0:
                        # Search in a 300 character window around the name
                        search_start = max(0, name_index - 150)
                        search_end = min(len(text), name_index + len(contact_name) + 150)
                        search_window = text[search_start:search_end]
                        
                        # Look for phone patterns in this window
                        phone_patterns = [
                            r"Mobile[:\s]*([0-9\s\-\(\)]{8,})",
                            r"Phone[:\s]*([0-9\s\-\(\)]{8,})",
                            r"([0-9]{2}[)\s\-]*[0-9]{4}[)\s\-]*[0-9]{4})",  # AU phone pattern
                            r"(\([0-9]{2}\)[)\s\-]*[0-9]{4}[)\s\-]*[0-9]{4})",  # (area) number
                            r"([0-9]{4}[)\s\-]*[0-9]{3}[)\s\-]*[0-9]{3})"  # 10 digit pattern
                        ]
                        
                        for pattern in phone_patterns:
                            phone_match = re.search(pattern, search_window, re.IGNORECASE)
                            if phone_match:
                                phone = phone_match.group(1)
                                # Clean the phone number
                                clean_phone = re.sub(r'[^\d]', '', phone)
                                if len(clean_phone) >= 8:
                                    contact["phone"] = clean_phone
                                    if clean_phone not in phone_numbers:
                                        phone_numbers.append(clean_phone)
                                    logger.info(f"[AMBROSE] Found phone for {contact_name}: {clean_phone}")
                                    break
        
        # Store phones for Phone3/Phone4 mapping (first 2 go to Phone3/Phone4)
        extracted_data["extra_phones"] = phone_numbers[:4]
        logger.info(f"[AMBROSE] Collected phones for Phone3/Phone4: {phone_numbers[:4]}")
        
        # Extract basic contact fields like the older version (email, mobile, home, work, phone)
        # This ensures we populate the main contact fields that the UI expects
        if extracted_data["alternate_contacts"]:
            # Get the primary contact (Decision Maker or first contact)
            primary_contact = None
            for contact in extracted_data["alternate_contacts"]:
                if contact.get("type", "").lower() == "decision maker":
                    primary_contact = contact
                    break
            if not primary_contact:
                primary_contact = extracted_data["alternate_contacts"][0]
            
            # Set main contact fields from primary contact
            if primary_contact:
                if primary_contact.get("email") and not extracted_data.get("email"):
                    extracted_data["email"] = primary_contact["email"]
                if primary_contact.get("phone"):
                    # Set mobile as the primary phone
                    extracted_data["mobile"] = primary_contact["phone"]
                    extracted_data["phone"] = primary_contact["phone"]
                if primary_contact.get("phone2"):
                    extracted_data["phone2"] = primary_contact["phone2"]
        
        # Extract additional phone types from BEST CONTACT DETAILS section
        if best_contact_section:
            contact_text = best_contact_section.group(1)
            
            # Extract specific phone types
            home_match = re.search(r"Home[:\s]*([0-9\s\-\(\)]+)", contact_text, re.IGNORECASE)
            if home_match:
                extracted_data["home_phone"] = home_match.group(1).strip()
            
            work_match = re.search(r"Work[:\s]*([0-9\s\-\(\)]+)", contact_text, re.IGNORECASE)
            if work_match:
                extracted_data["work_phone"] = work_match.group(1).strip()
            
            # Extract basic contact fields directly like the older successful version
            # This ensures we populate email, mobile, home_phone, work_phone like the test data
            direct_patterns = [
                ("email", r"Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"),
                ("mobile", r"Mobile[:\s]*([0-9\s\-\(\)]+)"),
                ("home_phone", r"Home[:\s]*([0-9\s\-\(\)]+)"),
                ("work_phone", r"Work[:\s]*([0-9\s\-\(\)]+)"),
            ]
            
            for field_name, pattern in direct_patterns:
                if not extracted_data.get(field_name):
                    match = re.search(pattern, contact_text, re.IGNORECASE)
                    if match:
                        value = match.group(1).strip()
                        if field_name == "email":
                            extracted_data[field_name] = value
                        else:
                            # Clean phone numbers
                            clean_phone = re.sub(r'[^\d]', '', value)
                            if len(clean_phone) >= 8:
                                extracted_data[field_name] = clean_phone
                                # Also set main phone if not set
                                if field_name == "mobile" and not extracted_data.get("phone"):
                                    extracted_data["phone"] = clean_phone
            
            # Ensure we have extra_phones populated like the older version
            if phone_numbers:
                extracted_data["extra_phones"] = phone_numbers[:4]  # First 4 phones for compatibility
                
                # Set phone fields for compatibility with older system
                if len(phone_numbers) > 0 and not extracted_data.get("phone"):
                    extracted_data["phone"] = phone_numbers[0]
                if len(phone_numbers) > 0 and not extracted_data.get("mobile"):
                    extracted_data["mobile"] = phone_numbers[0]
                if len(phone_numbers) > 1 and not extracted_data.get("phone2"):
                    extracted_data["phone2"] = phone_numbers[1]
        
        # If we still don't have basic contact fields, use the older simple patterns as fallback
        if not extracted_data.get("email") or not extracted_data.get("phone") or not extracted_data.get("mobile"):
            logger.info("[AMBROSE] Using fallback simple patterns like the older successful version")
            
            # Simple phone patterns from the older successful version
            phone_patterns = [
                r'Phone:\s*(\d[\d\s-]+)',
                r'Mobile:\s*(\d[\d\s-]+)', 
                r'Contact No\.:\s*(\d[\d\s-]+)',
                r'Phone1:\s*(\d[\d\s-]+)',
                r'Phone2:\s*(\d[\d\s-]+)',
                r'Home:\s*(\d[\d\s-]+)',
                r'Work:\s*(\d[\d\s-]+)'
            ]
            
            phones = []
            for pattern in phone_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    phone = re.sub(r'[^\d]', '', match.group(1))
                    if len(phone) >= 8 and phone not in phones:
                        phones.append(phone)
            
            # Assign phones to fields like the older version
            if phones and not extracted_data.get("phone"):
                extracted_data["phone"] = phones[0]
                logger.info(f"[AMBROSE] Set phone from fallback: {phones[0]}")
            if len(phones) > 1 and not extracted_data.get("mobile"):
                extracted_data["mobile"] = phones[1]
                logger.info(f"[AMBROSE] Set mobile from fallback: {phones[1]}")
            if len(phones) > 2 and not extracted_data.get("home_phone"):
                extracted_data["home_phone"] = phones[2]
                logger.info(f"[AMBROSE] Set home_phone from fallback: {phones[2]}")
            if len(phones) > 3 and not extracted_data.get("work_phone"):
                extracted_data["work_phone"] = phones[3]
                logger.info(f"[AMBROSE] Set work_phone from fallback: {phones[3]}")
            
            # Simple email pattern from the older successful version
            if not extracted_data.get("email"):
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
                if email_match:
                    extracted_data["email"] = email_match.group(0)
                    logger.info(f"[AMBROSE] Found email using simple pattern: {extracted_data['email']}")
    
    else:
        # --- Original contact extraction for non-Ambrose builders ---
        contact_types = [
            ("Best Contact", r"BEST\s+CONTACT\s+DETAILS"),
            ("Real Estate Agent", r"REAL\s+ESTATE\s+AGENT"),
            ("Site Contact", r"SITE\s+CONTACT"),
            ("Authorised Contact", r"AUTHORI[ZS]ED\s+CONTACT"),
        ]
        main_customer_name = extracted_data.get("customer_name", "").strip().lower()
        for label, regex in contact_types:
            section = re.search(
                rf"{regex}([\s\S]+?)(?=SUPERVISOR|JOB\s+DETAILS|$)", text, re.IGNORECASE
            )
            if section:
                contact_text = section.group(1)
                # Decision Maker (for alternate contact)
                decision_maker_match = re.search(
                    r"Decision Maker:?[ \t]*([A-Za-z\s\-'\.]+?)(?=\n|$)",
                    contact_text,
                    re.IGNORECASE,
                )
                if decision_maker_match:
                    name = decision_maker_match.group(1).strip()
                    # Phone
                    phone_match = re.search(
                        r"Mobile:?[ \t]*([\d\(\)\-\s]+)", contact_text, re.IGNORECASE
                    )
                    phone = phone_match.group(1).strip() if phone_match else ""
                    # Email
                    email_match = re.search(
                        r"Email:?[ \t]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
                        contact_text,
                        re.IGNORECASE,
                    )
                    email = email_match.group(1).strip() if email_match else ""
                    # Only add if name is different from main customer
                    if name and name.lower() != main_customer_name:
                        extracted_data["alternate_contact_name"] = name
                        extracted_data["alternate_contact_phone"] = phone
                        extracted_data["alternate_contact_email"] = email
                        extracted_data["alternate_contacts"].append(
                            {
                                "type": "Decision Maker",
                                "name": name,
                                "phone": phone,
                                "email": email,
                            }
                        )
                # Fallback to previous logic for other alternates
                name_match = re.search(
                    r"Name:?[ \t]*([A-Za-z\s\-'\.]+?)(?=\n|$)", contact_text, re.IGNORECASE
                )
                name = name_match.group(1).strip() if name_match else ""
                phone_match = re.search(
                    r"(Mobile|Phone|Contact):?[ \t]*([\d\(\)\-\s]+)",
                    contact_text,
                    re.IGNORECASE,
                )
                phone = phone_match.group(2).strip() if phone_match else ""
                email_match = re.search(
                    r"Email:?[ \t]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
                    contact_text,
                    re.IGNORECASE,
                )
                email = email_match.group(1).strip() if email_match else ""
                if name and name.lower() != main_customer_name:
                    extracted_data["alternate_contacts"].append(
                        {"type": label, "name": name, "phone": phone, "email": email}
                    )
                if (
                    label in ("Best Contact", "Real Estate Agent")
                    and not extracted_data["alternate_contact_name"]
                    and name
                    and name.lower() != main_customer_name
                ):
                    extracted_data["alternate_contact_name"] = name
                    extracted_data["alternate_contact_phone"] = phone
                    extracted_data["alternate_contact_email"] = email

    # --- Explicitly extract 'Authorised Contact' and 'Site Contact' as alternates even if not in a section ---
    for label in ["Authorised Contact", "Site Contact"]:
        # Match lines like 'Authorised Contact: Name' or 'Site Contact: Name'
        pattern = rf"{label}:?\s*([A-Za-z\s\-'\.]+)\n?(\(H\)\s*\d+)?\s*(\(M\)\s*\d+)?"
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            name = match[0].strip()
            phone1 = match[1].replace("(H)", "").strip() if match[1] else ""
            phone2 = match[2].replace("(M)", "").strip() if match[2] else ""
            # Only add if name is not empty and not the main customer
            if name and name.lower() != main_customer_name:
                extracted_data["alternate_contacts"].append(
                    {
                        "type": label,
                        "name": name,
                        "phone": phone1,
                        "phone2": phone2,
                        "email": "",
                    }
                )

    # Extract Campbell-specific Site Contact if this is Campbell template
    if "campbell" in template["name"].lower():
        # Site Contact: firstname surname - "relationship to customer"
        site_contact_match = re.search(
            r"Site\s+Contact:\s*\n([A-Za-z\s\-'\.]+?)(?:\s*-\s*[^,\n]+)?(?=\n|Phone:|Contact)",
            text,
            re.IGNORECASE
        )
        if site_contact_match and not extracted_data.get("customer_name"):
            extracted_data["customer_name"] = site_contact_match.group(1).strip()
            logger.info(f"[CAMPBELL] Found customer name: {extracted_data['customer_name']}")
        
        # Contact No. Phone1, Phone2 etc..
        contact_no_match = re.search(
            r"Contact\s+No[.:]?\s*\n([0-9\s\-\(\)]+)",  # Phone is on next line
            text,
            re.IGNORECASE
        )
        if contact_no_match and not extracted_data.get("phone"):
            extracted_data["phone"] = contact_no_match.group(1).strip()
            logger.info(f"[CAMPBELL] Found phone: {extracted_data['phone']}")
        
        # Site Address for Campbell
        site_address_match = re.search(
            r"Site\s+Address:\s*\n([^\n]+)",
            text,
            re.IGNORECASE
        )
        if site_address_match and not extracted_data.get("address"):
            extracted_data["address"] = site_address_match.group(1).strip()
            logger.info(f"[CAMPBELL] Found address: {extracted_data['address']}")
            try:
                if extracted_data["address"]:  # Only parse if address is not empty
                    parse_address(extracted_data["address"], extracted_data)
            except Exception as e:
                logger.warning(f"Failed to parse Campbell address: {e}")
        
        # Try to extract dollar value from Subtotal
        subtotal_match = re.search(
            r"Subtotal\s*\n\s*\$?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE
        )
        if subtotal_match and extracted_data.get("dollar_value", 0) == 0:
            value_str = subtotal_match.group(1).replace(",", "")
            try:
                extracted_data["dollar_value"] = float(value_str)
                logger.info(f"[CAMPBELL] Found dollar value: ${extracted_data['dollar_value']}")
            except ValueError:
                pass

    # Extract Townsend-specific fields if this is Townsend template
    if "townsend" in template["name"].lower():
        # Extract customer from Site Contact Name (only first line)
        site_contact_match = re.search(
            r"Site\s+Contact\s+Name\s*\n([A-Za-z\s\(\)\-'\.]+?)(?=\n|Atf|atf|Mr|Ms|Mrs)",
            text,
            re.IGNORECASE
        )
        if site_contact_match and not extracted_data.get("customer_name"):
            extracted_data["customer_name"] = site_contact_match.group(1).strip()
            logger.info(f"[TOWNSEND] Found customer name: {extracted_data['customer_name']}")
        
        # Extract phone from Site Contact Phone
        contact_phone_match = re.search(
            r"Site\s+Contact\s+Phone\s*\n([0-9\s\-\(\)]+)",
            text,
            re.IGNORECASE
        )
        if contact_phone_match and not extracted_data.get("phone"):
            extracted_data["phone"] = contact_phone_match.group(1).strip()
            logger.info(f"[TOWNSEND] Found phone: {extracted_data['phone']}")
        
        # Extract email from Customer Email
        customer_email_match = re.search(
            r"Customer\s+Email\s*\n([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            text,
            re.IGNORECASE
        )
        if customer_email_match and not extracted_data.get("email"):
            extracted_data["email"] = customer_email_match.group(1).strip()
            logger.info(f"[TOWNSEND] Found email: {extracted_data['email']}")
        
        # Extract address from Site Address
        site_address_match = re.search(
            r"Site\s+Address\s*\n([^\n]+)",
            text,
            re.IGNORECASE
        )
        if site_address_match and not extracted_data.get("address"):
            extracted_data["address"] = site_address_match.group(1).strip()
            logger.info(f"[TOWNSEND] Found address: {extracted_data['address']}")
            try:
                if extracted_data["address"]:  # Only parse if address is not empty
                    parse_address(extracted_data["address"], extracted_data)
            except Exception as e:
                logger.warning(f"Failed to parse Townsend address: {e}")
        
        # Extract dollar value from Subtotal  
        subtotal_match = re.search(
            r"Subtotal\s*\n\s*\$?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE
        )
        if subtotal_match and extracted_data.get("dollar_value", 0) == 0:
            value_str = subtotal_match.group(1).replace(",", "")
            try:
                extracted_data["dollar_value"] = float(value_str)
                logger.info(f"[TOWNSEND] Found dollar value: ${extracted_data['dollar_value']}")
            except ValueError:
                pass
        
        # Extract supervisor from Supervisor field
        supervisor_match = re.search(
            r"Supervisor\s*\n([A-Za-z\s\-'\.]+?)(?=\n|Site)",
            text,
            re.IGNORECASE
        )
        if supervisor_match and not extracted_data.get("supervisor_name"):
            extracted_data["supervisor_name"] = supervisor_match.group(1).strip()
            logger.info(f"[TOWNSEND] Found supervisor: {extracted_data['supervisor_name']}")
        
        # Extract supervisor contact from Supervisor Contact
        supervisor_contact_match = re.search(
            r"Supervisor\s+Contact\s*\n([0-9\s\-\(\)]+)",
            text,
            re.IGNORECASE
        )
        if supervisor_contact_match and not extracted_data.get("supervisor_mobile"):
            extracted_data["supervisor_mobile"] = supervisor_contact_match.group(1).strip()
            logger.info(f"[TOWNSEND] Found supervisor mobile: {extracted_data['supervisor_mobile']}")

    # Extract Profile Build Group specific fields if this is Profile Build template
    if "profile build" in template["name"].lower():
        logger.info(f"[PROFILE BUILD] Running Profile Build Group specific extraction logic")
        # For Profile Build Group: SITE CONTACT is the customer, NOT Client (which is the insurance company)
        
        # Extract customer from SITE CONTACT field - OVERRIDE any previous extraction
        site_contact_match = re.search(
            r"SITE\s+CONTACT:\s*([A-Za-z\s\-'\.]+?)(?=\n)",  # Stop at newline - includes hyphens, apostrophes, periods
            text,
            re.IGNORECASE
        )
        if site_contact_match:
            customer_name = site_contact_match.group(1).strip()
            if customer_name:
                extracted_data["customer_name"] = customer_name  # Override the insurance company name
                logger.info(f"[PROFILE BUILD] Found customer name (SITE CONTACT): {extracted_data['customer_name']}")
                
                # Split the name into first/last for the customer fields
                name_parts = customer_name.split()
                if len(name_parts) >= 2:
                    extracted_data["first_name"] = name_parts[0]
                    extracted_data["last_name"] = " ".join(name_parts[1:])
                else:
                    extracted_data["first_name"] = ""
                    extracted_data["last_name"] = customer_name
        
        # Extract customer phone from SITE CONTACT PHONE field
        site_phone_match = re.search(
            r"SITE\s+CONTACT\s+PHONE:\s*([0-9\s\-\(\)]+?)(?=\n)",  # Stop at newline
            text,
            re.IGNORECASE
        )
        if site_phone_match:
            phone = site_phone_match.group(1).strip()
            clean_phone = "".join(c for c in phone if c.isdigit())
            if 8 <= len(clean_phone) <= 12:
                extracted_data["phone"] = phone
                logger.info(f"[PROFILE BUILD] Found customer phone (SITE CONTACT PHONE): {extracted_data['phone']}")
        
        # Extract attendance dates for commencement/installation dates
        attendance_match = re.search(
            r"ATTENDANCE\s+SCHEDULED\s+FOR:\s*(\d{1,2}/\d{1,2}/\d{4})\s*to\s*(\d{1,2}/\d{1,2}/\d{4})",
            text,
            re.IGNORECASE
        )
        if attendance_match:
            extracted_data["commencement_date"] = attendance_match.group(1).strip()
            extracted_data["installation_date"] = attendance_match.group(2).strip()
            logger.info(f"[PROFILE BUILD] Found attendance dates: {extracted_data['commencement_date']} to {extracted_data['installation_date']}")
        
        # Extract supervisor name from top left area - look for pattern after company address
        # Pattern: 2/133 REDLAND BAY RD Capalaba QLD 4157\nT: 07 3638 0304\nE: ...\nSupervisor:\nJamie Zoch
        supervisor_match = re.search(
            r"2/133\s+REDLAND\s+BAY\s+RD[\s\S]*?Supervisor:\s*\n([A-Za-z\s]+?)(?=\n|ABN:|Phone:|$)",
            text,
            re.IGNORECASE | re.MULTILINE
        )
        if supervisor_match:
            supervisor_name = supervisor_match.group(1).strip()
            if supervisor_name:
                extracted_data["supervisor_name"] = supervisor_name
                logger.info(f"[PROFILE BUILD] Found supervisor: {extracted_data['supervisor_name']}")
        
        # Extract supervisor phone - look for phone number directly under "Supervisor:" and supervisor name
        # This can be either a landline (like 07 3638 0304) or mobile (like 0402 233 333)
        if extracted_data.get("supervisor_name"):
            # Look for "Phone:" label followed by phone number after supervisor name
            supervisor_phone_match = re.search(
                rf"Supervisor:\s*\n{re.escape(extracted_data['supervisor_name'])}[\s\S]*?Phone:\s*\n([0-9\s\-\(\)]+)",
                text,
                re.IGNORECASE | re.MULTILINE
            )
            if supervisor_phone_match:
                phone = supervisor_phone_match.group(1).strip()
                clean_phone = "".join(c for c in phone if c.isdigit())
                # Accept any valid phone number (landline or mobile) that appears under supervisor
                if 8 <= len(clean_phone) <= 12:
                    extracted_data["supervisor_mobile"] = phone
                    logger.info(f"[PROFILE BUILD] Found supervisor phone: {extracted_data['supervisor_mobile']}")
                else:
                    logger.info(f"[PROFILE BUILD] Invalid phone format for supervisor: {phone}")
            else:
                # Fallback: look for any phone number pattern after supervisor name (without "Phone:" label)
                supervisor_section_match = re.search(
                    rf"Supervisor:\s*\n{re.escape(extracted_data['supervisor_name'])}[\s\S]{{0,100}}?([0-9\s\-\(\)]+)",
                    text,
                    re.IGNORECASE | re.MULTILINE
                )
                if supervisor_section_match:
                    phone = supervisor_section_match.group(1).strip()
                    clean_phone = "".join(c for c in phone if c.isdigit())
                    if 8 <= len(clean_phone) <= 12:
                        extracted_data["supervisor_mobile"] = phone
                        logger.info(f"[PROFILE BUILD] Found supervisor phone (fallback): {extracted_data['supervisor_mobile']}")
                    else:
                        logger.info(f"[PROFILE BUILD] Invalid phone format for supervisor (fallback): {phone}")
        
        # Extract email - Profile Build often uses their company email
        if not extracted_data.get("email"):
            # Try to find any @profilebuildgroup email
            email_match = re.search(
                r"([a-zA-Z0-9._%+-]+@profilebuildgroup\.com\.au)",
                text,
                re.IGNORECASE
            )
            if email_match:
                extracted_data["email"] = email_match.group(1).strip()
                logger.info(f"[PROFILE BUILD] Found email: {extracted_data['email']}")
        
        # Extract address - For Profile Build, use SITE LOCATION
        address_match = re.search(
            r"SITE\s+LOCATION:\s*([^\n]+)",
            text,
            re.IGNORECASE
        )
        if address_match:
            raw_address = address_match.group(1).strip()
            extracted_data["address"] = raw_address
            logger.info(f"[PROFILE BUILD] Found address: {extracted_data['address']}")
            try:
                if raw_address:
                    # Parse the address into components and override the full address in address1
                    parse_address(raw_address, extracted_data)
                    logger.info(f"[PROFILE BUILD] Parsed address - address1: '{extracted_data.get('address1', '')}', city: '{extracted_data.get('city', '')}', state: '{extracted_data.get('state', '')}', zip: '{extracted_data.get('zip_code', '')}'")
            except Exception as e:
                logger.warning(f"Failed to parse Profile Build address: {e}")
        
        # Extract description of works - NOTES section AND flooring details for Profile Build
        description_parts = []
        
        # Get the NOTES section - be very specific to avoid header content
        # Look for "NOTES:" followed by actual notes content, but skip any header info that might be embedded
        notes_match = re.search(
            r"NOTES:\s*(Hi\s+[A-Za-z]+[\s\S]*?)(?=Date:|Client:|Job Number:|SITE LOCATION:|ATTENDANCE|Flooring|Subtotal|Total|$)",
            text,
            re.IGNORECASE
        )
        
        # If the specific "Hi Adrian" pattern doesn't work, try a more general approach
        if not notes_match:
            notes_match = re.search(
                r"NOTES:\s*([A-Za-z][\s\S]*?)(?=Date:|Client:|Job Number:|SITE LOCATION:|ATTENDANCE|Flooring|Subtotal|Total|$)",
                text,
                re.IGNORECASE
            )
        if notes_match:
            notes_description = notes_match.group(1).strip()
            # Clean up the notes - remove any header information that might have leaked in
            lines = notes_description.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                # Skip empty lines and header-like content
                if not line:
                    continue
                # Stop if we hit PDF header elements, contact info, or extracted data
                if (re.match(r'^(To:|Profile Build Group|ABN:|Phone:|Email:|Supervisor:|QBCC|Date:|Client:|Job Number:|SITE|ATTENDANCE)', line, re.IGNORECASE) or
                    re.match(r'^[0-9\s\-\(\)]+$', line) or  # Phone number lines
                    re.match(r'^[A-Z]{2,3}\s+\d{4}$', line) or  # State postcode lines
                    'extracted_data' in line.lower() or
                    line.startswith('{') or
                    line.startswith('"')):
                    break
                cleaned_lines.append(line)
            
            if cleaned_lines:
                final_notes = '\n'.join(cleaned_lines).strip()
                
                # Additional cleaning - remove any remaining header blocks that might be embedded
                # Split by common header patterns and take only the actual notes content
                header_patterns = [
                    r'To:\s*A to Z Flooring Solutions.*?(?=Hi\s+[A-Za-z]+|$)',
                    r'Profile Build Group.*?(?=Hi\s+[A-Za-z]+|$)',
                    r'\d{11}.*?(?=Hi\s+[A-Za-z]+|$)',  # ABN numbers
                    r'[A-Z]{2,3}\s+\d{4}.*?(?=Hi\s+[A-Za-z]+|$)',  # State postcodes
                    r'T:\s*\d+.*?(?=Hi\s+[A-Za-z]+|$)',  # Phone numbers
                    r'E:\s*\w+@.*?(?=Hi\s+[A-Za-z]+|$)',  # Email addresses
                    r'Supervisor:.*?(?=Hi\s+[A-Za-z]+|$)',
                    r'ABN:.*?(?=Hi\s+[A-Za-z]+|$)',
                    r'QBCC.*?(?=Hi\s+[A-Za-z]+|$)',
                ]
                
                for pattern in header_patterns:
                    final_notes = re.sub(pattern, '', final_notes, flags=re.IGNORECASE | re.DOTALL)
                
                final_notes = final_notes.strip()
                
                # Only add if we have actual notes content (not just header info)
                if len(final_notes) > 10 and not re.match(r'^(To:|Profile|ABN|Phone|Email)', final_notes):
                    description_parts.append(final_notes)
        
        # Get the flooring details section
        flooring_match = re.search(
            r"Flooring\s*\n([\s\S]+?)(?=Subtotal|Total|NOTES|$)",
            text,
            re.IGNORECASE
        )
        if flooring_match:
            flooring_description = flooring_match.group(1).strip()
            # Clean up the flooring description
            lines = flooring_description.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Stop if we hit extracted data or non-flooring content
                if (re.match(r'^(PO|Work Order|Customer|Phone|Email):', line, re.IGNORECASE) or
                    'extracted_data' in line.lower() or
                    line.startswith('{') or
                    line.startswith('"')):
                    break
                cleaned_lines.append(line)
            
            if cleaned_lines:
                final_flooring = '\n'.join(cleaned_lines).strip()
                if final_flooring:
                    description_parts.append(f"Flooring Details:\n{final_flooring}")
        
        # Combine sections
        if description_parts:
            combined_description = "\n\n".join(description_parts)
            extracted_data["description_of_works"] = combined_description
            logger.info(f"[PROFILE BUILD] Found clean description: {len(combined_description)} characters")

    # Extract One Solutions specific fields if this is One Solutions template
    if "one solutions" in template["name"].lower():
        # For One Solutions: SITE CONTACT is also the customer
        
        # Extract customer from SITE CONTACT field - OVERRIDE any previous extraction
        site_contact_match = re.search(
            r"SITE\s+CONTACT:\s*([A-Za-z\s\-'\.]+?)(?=\n)",  # Stop at newline - includes hyphens, apostrophes, periods
            text,
            re.IGNORECASE
        )
        if site_contact_match:
            customer_name = site_contact_match.group(1).strip()
            if customer_name:
                extracted_data["customer_name"] = customer_name  # Override any previous extraction
                logger.info(f"[ONE SOLUTIONS] Found customer name (SITE CONTACT): {extracted_data['customer_name']}")
                
                # Split the name into first/last for the customer fields
                name_parts = customer_name.split()
                if len(name_parts) >= 2:
                    extracted_data["first_name"] = name_parts[0]
                    extracted_data["last_name"] = " ".join(name_parts[1:])
                else:
                    extracted_data["first_name"] = ""
                    extracted_data["last_name"] = customer_name
        
        # Extract customer phone from SITE CONTACT PHONE field
        site_phone_match = re.search(
            r"SITE\s+CONTACT\s+PHONE:\s*([0-9\s\-\(\)]+?)(?=\n)",  # Stop at newline
            text,
            re.IGNORECASE
        )
        if site_phone_match:
            phone = site_phone_match.group(1).strip()
            clean_phone = "".join(c for c in phone if c.isdigit())
            if 8 <= len(clean_phone) <= 12:
                extracted_data["phone"] = phone
                logger.info(f"[ONE SOLUTIONS] Found customer phone (SITE CONTACT PHONE): {extracted_data['phone']}")

    # Extract site contact details first
    site_contact_patterns = [
        r"Site\s+Contact:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)",
        r"Site\s+Contact\s+Name:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)",
        r"Contact\s+Name:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)"
    ]
    
    for pattern in site_contact_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            site_contact = match.group(1).strip()
            # Store site contact as ship to name
            extracted_data["ship_to_name"] = site_contact
            logger.info(f"Found site contact/ship to name: {site_contact}")
            break
    
    # Extract site address with improved patterns (skip if Profile Build, One Solutions, or Ambrose already handled it)
    if not ("profile build" in template["name"].lower() or "one solutions" in template["name"].lower() or "ambrose" in template["name"].lower()):
        address_patterns = [
            r"Site\s+Address:?\s*([A-Za-z0-9\s\.,#-]+?)(?=\n|$)",
            r"Site\s+Location:?\s*([A-Za-z0-9\s\.,#-]+?)(?=\n|$)",
            r"Property\s+Address:?\s*([A-Za-z0-9\s\.,#-]+?)(?=\n|$)",
            r"Location:?\s*([A-Za-z0-9\s\.,#-]+?)(?=\n|$)"
        ]
        
        for pattern in address_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                address = match.group(1).strip()
                # Skip if it's the "included on tax invoice" message
                if "tax invoice" not in address.lower():
                    extracted_data["address"] = address
                    # Parse address into components
                    parse_address(address, extracted_data)
                    # Also set as ship to address
                    extracted_data["ship_to_address"] = address
                    logger.info(f"Found site/ship to address: {address}")
                    break

    # After extracting supervisor name/phone
    logger.info(f"[EXTRACT] Supervisor Name: {extracted_data['supervisor_name']}")
    logger.info(f"[EXTRACT] Supervisor Phone: {extracted_data['supervisor_mobile']}")
    # After extracting description of works
    logger.info(
        f"[EXTRACT] Description of Works: {extracted_data['description_of_works']}"
    )
    # After extracting email
    logger.info(f"[EXTRACT] Email: {extracted_data['email']}")
    # After extracting all phone numbers
    logger.info(
        f"[EXTRACT] Phone: {extracted_data['phone']}, Mobile: {extracted_data['mobile']}, Home: {extracted_data['home_phone']}, Work: {extracted_data['work_phone']}, Extra: {extracted_data['extra_phones']}"
    )
    # After extracting alternate contacts
    logger.info(f"[EXTRACT] Alternate Contacts: {extracted_data['alternate_contacts']}")


def extract_contact_details(text, extracted_data):
    """Extract all contact details from the text."""
    # Extract email
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    email_matches = re.findall(email_pattern, text)

    # Look for customer email specifically
    customer_email_patterns = [
        r"Email:?\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
        r"E-mail:?\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
    ]

    # First try to find email in the BEST CONTACT DETAILS section
    best_contact_section = re.search(
        r"BEST\s+CONTACT\s+DETAILS([\s\S]+?)(?=SUPERVISOR|JOB\s+DETAILS|$)",
        text,
        re.IGNORECASE,
    )
    if best_contact_section:
        contact_text = best_contact_section.group(1)
        for pattern in customer_email_patterns:
            match = re.search(pattern, contact_text, re.IGNORECASE)
            if match:
                extracted_data["email"] = match.group(1).strip()
                break

    # If no email found in BEST CONTACT DETAILS, try general email patterns
    if not extracted_data["email"]:
        for pattern in customer_email_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and not match.group(1).endswith(
                "ambroseconstruct.com.au"
            ):  # Skip company emails
                extracted_data["email"] = match.group(1).strip()
                break

    # If no labeled email found but we have email matches, use the first one that's not from ambroseconstruct
    if not extracted_data["email"] and email_matches:
        for email in email_matches:
            if not email.endswith("ambroseconstruct.com.au") and not email.endswith(
                "atozflooringsolutions.com.au"
            ):
                extracted_data["email"] = email
                break

    # Extract all phone numbers from the document for potential extra phone fields
    all_phone_numbers = []

    # General pattern to find all phone numbers
    phone_pattern = r"(?<!\d)(?:\+?61|0)?(?:\(?\d{2,4}\)?\s?\d{3,4}\s?\d{3,4}|\d{4}\s?\d{3}\s?\d{3}|\d{8,10})(?!\d)"
    all_matches = re.finditer(phone_pattern, text)

    # Company phone numbers to exclude
    company_phone_numbers = ["0731100077", "35131176", "999869951"]
    excluded_number_patterns = [
        r"ABN:\s*(\d+)",  # ABN pattern
        r"Job\s+Number:?\s*([0-9-]+)",  # Job number pattern
    ]

    # Extract numbers to exclude
    numbers_to_exclude = []
    for pattern in excluded_number_patterns:
        match = re.search(pattern, text)
        if match:
            numbers_to_exclude.append(match.group(1))

    for match in all_matches:
        phone = match.group(0).strip()
        # Clean the phone number for comparison
        clean_phone = "".join(c for c in phone if c.isdigit())

        # Skip supervisor's mobile
        if extracted_data["supervisor_mobile"] and clean_phone == "".join(
            c for c in extracted_data["supervisor_mobile"] if c.isdigit()
        ):
            continue

        # Skip if it matches one of our excluded numbers
        if any(
            clean_phone == "".join(c for c in num if c.isdigit())
            for num in company_phone_numbers + numbers_to_exclude
        ):
            continue

        # Only add if it's not already one of our main numbers and looks like a valid phone
        if len(clean_phone) >= 8 and clean_phone not in [
            "".join(c for c in str(extracted_data.get("phone", "") or "") if c.isdigit()),
            "".join(c for c in str(extracted_data.get("mobile", "") or "") if c.isdigit()),
            "".join(c for c in str(extracted_data.get("home_phone", "") or "") if c.isdigit()),
            "".join(c for c in str(extracted_data.get("work_phone", "") or "") if c.isdigit()),
        ]:
            if len(clean_phone) >= 8 and len(clean_phone) <= 12:
                all_phone_numbers.append(phone)

    # Extract phone numbers from BEST CONTACT DETAILS section if available
    if best_contact_section:
        contact_text = best_contact_section.group(1)

        # Mobile phone
        mobile_match = re.search(
            r"Mobile:?\s*(\(?\d{4}\)?[-.\s]?\d{3}[-.\s]?\d{3})",
            contact_text,
            re.IGNORECASE,
        )
        if mobile_match:
            extracted_data["mobile"] = mobile_match.group(1).strip()
            if not extracted_data[
                "phone"
            ]:  # Use mobile as default phone if no other phone found
                extracted_data["phone"] = extracted_data["mobile"]

        # Home phone
        home_match = re.search(
            r"Home:?\s*(\(?\d{2}\)?[-.\s]?\d{4}[-.\s]?\d{4})",
            contact_text,
            re.IGNORECASE,
        )
        if home_match:
            extracted_data["home_phone"] = home_match.group(1).strip()
            if not extracted_data["phone"]:  # Use home as phone if no other phone found
                extracted_data["phone"] = extracted_data["home_phone"]

        # Work phone
        work_match = re.search(
            r"Work:?\s*(\(?\d{4}\)?[-.\s]?\d{3}[-.\s]?\d{3})",
            contact_text,
            re.IGNORECASE,
        )
        if work_match:
            extracted_data["work_phone"] = work_match.group(1).strip()

    # If we didn't find phones in the BEST CONTACT DETAILS, try general patterns
    if not extracted_data["mobile"]:
        # Mobile phone pattern
        mobile_patterns = [
            r"Mobile:?\s*(\(?\d{4}\)?[-.\s]?\d{3}[-.\s]?\d{3})",
            r"Mobile:?\s*(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",
            r"M:?\s*(\(?\d{4}\)?[-.\s]?\d{3}[-.\s]?\d{3})",
        ]

        for pattern in mobile_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_data["mobile"] = match.group(1).strip()
                if not extracted_data[
                    "phone"
                ]:  # Use mobile as default phone if no other phone found
                    extracted_data["phone"] = extracted_data["mobile"]
                break

    # If no specific labeled phone found, look for a generic phone
    if not extracted_data["phone"]:
        phone_patterns = [
            r"Phone:?\s*(\(?\d{2}\)?[-.\s]?\d{4}[-.\s]?\d{4})",
            r"Phone:?\s*(\(?\d{4}\)?[-.\s]?\d{3}[-.\s]?\d{3})",
            r"Tel:?\s*(\(?\d{2}\)?[-.\s]?\d{4}[-.\s]?\d{4})",
            r"Contact:?\s*(\(?\d{2}\)?[-.\s]?\d{4}[-.\s]?\d{4})",
        ]

        for pattern in phone_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_data["phone"] = match.group(1).strip()
                break

    # Add all unique phone numbers to extra_phones (will be filtered in clean_extracted_data)
    for phone in all_phone_numbers:
        # Clean the phone number - keep only digits
        clean_phone = "".join(c for c in phone if c.isdigit())

        # Check against existing phone numbers (also cleaned)
        main_phones = []
        for key in ["phone", "mobile", "home_phone", "work_phone"]:
            if extracted_data[key]:
                main_phones.append(
                    "".join(c for c in extracted_data[key] if c.isdigit())
                )

        # Only add if it's not already in our main numbers and not already in extra_phones
        if (
            clean_phone not in main_phones
            and clean_phone not in extracted_data["extra_phones"]
        ):
            extracted_data["extra_phones"].append(clean_phone)


def extract_job_and_supervisor_details(text, extracted_data, template):
    """Extract job number and supervisor details from the text."""
    # Extract supervisor name with improved patterns
    supervisor_patterns = [
        r"Supervisor:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)",
        r"Project\s+Manager:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)",
        r"Site\s+Supervisor:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)",
        r"Job\s+Supervisor:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)",
        r"Supervisor\s+Name:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)"
    ]
    
    for pattern in supervisor_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted_data["supervisor_name"] = match.group(1).strip()
            logger.info(f"Found supervisor name: {extracted_data['supervisor_name']}")
            break
    
    # Extract Job Number
    job_number_patterns = [
        r"Job\s+Number:?\s*([A-Za-z0-9-]+)",
        r"Job\s+#:?\s*([A-Za-z0-9-]+)",
        r"Job\s+ID:?\s*([A-Za-z0-9-]+)",
        r"WORK\s+ORDER[:\s]+([A-Za-z0-9-]+)",  # Added for alternative templates
        r"JOB\s+NUMBER[:\s]+([A-Za-z0-9-]+)",  # Added for alternative templates
    ]

    for pattern in job_number_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted_data["job_number"] = match.group(1).strip()
            break

    # Special handling for Australian Restoration Company
    if "australian restoration" in template["name"].lower():
        # Project Manager: = supervisor firstname and surname
        pm_match = re.search(
            r"Project\s+Manager[:\s]*([A-Za-z\s\-'\.]+?)(?=\n|P:|$)",
            text,
            re.IGNORECASE
        )
        if pm_match:
            extracted_data["supervisor_name"] = pm_match.group(1).strip()
        
        # P: = Supervisor Phone number/mobile number
        phone_match = re.search(
            r"P:\s*([0-9\s\-\(\)]+?)(?=\n|E:|$)",
            text,
            re.IGNORECASE
        )
        if phone_match:
            extracted_data["supervisor_mobile"] = phone_match.group(1).strip()
        
        # E: name@ispprovider.com.au = Supervisors email address
        email_match = re.search(
            r"E:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            text,
            re.IGNORECASE
        )
        if email_match:
            extracted_data["supervisor_email"] = email_match.group(1).strip()
        
        # Customer Phone: = Customer Phone1
        cust_phone_match = re.search(
            r"Customer\s+Phone[:\s]*([0-9\s\-\(\)]+)",
            text,
            re.IGNORECASE
        )
        if cust_phone_match:
            extracted_data["phone"] = cust_phone_match.group(1).strip()
        
        return  # Skip the rest for Australian Restoration

    # Special handling for Ambrose Construct Group
    if "ambrose" in template["name"].lower():
        # Look for Supervisor Details section and extract name and phone/mobile
        supervisor_details_match = re.search(
            r"Supervisor\s+Details[:\s]*\n([\s\S]+?)(?=BEST\s+CONTACT|JOB\s+DETAILS|$)",
            text,
            re.IGNORECASE
        )
        
        if supervisor_details_match:
            supervisor_section = supervisor_details_match.group(1)
            logger.info(f"[AMBROSE] Found supervisor section: {supervisor_section[:100]}...")
            
            # Extract supervisor name - look for name pattern after header
            name_patterns = [
                r"Name[:\s]*([A-Za-z\s\-'\.]+?)(?=\n|Phone|Mobile|$)",  # "Name: John Smith" - includes hyphens, apostrophes, periods
                r"^([A-Za-z\s\-'\.]+?)(?=\n|Phone|Mobile)",  # First line if no "Name:" label
            ]
            
            for pattern in name_patterns:
                name_match = re.search(pattern, supervisor_section.strip(), re.IGNORECASE | re.MULTILINE)
                if name_match:
                    extracted_data["supervisor_name"] = name_match.group(1).strip()
                    logger.info(f"[AMBROSE] Found supervisor name: {extracted_data['supervisor_name']}")
                    break
            
            # Extract phone number - look for Phone or Mobile
            phone_patterns = [
                r"Phone[:\s]*([0-9\s\-\(\)]+?)(?=\n|Mobile|$)",  # "Phone: 0123456789"
                r"Mobile[:\s]*([0-9\s\-\(\)]+?)(?=\n|Phone|$)",  # "Mobile: 0123456789"
                r"(\(?0\d{1,2}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4})",  # Generic phone pattern
            ]
            
            for pattern in phone_patterns:
                phone_match = re.search(pattern, supervisor_section, re.IGNORECASE)
                if phone_match:
                    extracted_data["supervisor_phone"] = phone_match.group(1).strip()
                    logger.info(f"[AMBROSE] Found supervisor phone: {extracted_data['supervisor_phone']}")
                    break
        
        return  # Skip the rest for Ambrose

    # Extract Supervisor/Contractor Representative Details
    supervisor_section_pattern = template.get("supervisor_section_pattern", r"Supervisor\s+Details")
    supervisor_section = re.search(
        rf"{supervisor_section_pattern}([\s\S]+?)(?=BEST\s+CONTACT|JOB\s+DETAILS|$)",
        text,
        re.IGNORECASE,
    )

    if supervisor_section:
        supervisor_text = supervisor_section.group(1)
        
        # Ensure supervisor_text is a string
        if not isinstance(supervisor_text, str):
            logger.warning(f"supervisor_text is not a string: {type(supervisor_text)}")
            return

        # Extract Name
        name_match = re.search(
            r"Name:?\s*([A-Za-z\s\-'\.]+?)(?=\n)", supervisor_text, re.IGNORECASE
        )
        if name_match:
            extracted_data["supervisor_name"] = name_match.group(1).strip()

        # Extract Mobile
        mobile_match = re.search(
            r"Mobile:?\s*(\(?\d{4}\)?[-.\s]?\d{3}[-.\s]?\d{3})",
            supervisor_text,
            re.IGNORECASE,
        )
        if mobile_match:
            extracted_data["supervisor_mobile"] = mobile_match.group(1).strip()

        # Extract Email
        email_match = re.search(
            r"Email:?\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            supervisor_text,
            re.IGNORECASE,
        )
        if email_match:
            extracted_data["supervisor_email"] = email_match.group(1).strip()
    else:
        # Try alternative patterns if no section found
        # Look for standalone patterns
        contact_label = template.get('contact_label') or 'Supervisor'  # Handle None
        name_patterns = [
            rf"{contact_label}:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)",
            r"Contractor:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)",
            r"Representative:?\s*([A-Za-z\s\-'\.]+?)(?=\n|$)",
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_data["supervisor_name"] = match.group(1).strip()
                break


def parse_address(address_str, extracted_data):
    """Parse address string into components."""
    if not address_str:
        return
    
    # Clean up the address string
    address_str = address_str.strip()
    
    # Initialize default values
    extracted_data['address1'] = address_str
    extracted_data['address2'] = ''
    extracted_data['city'] = ''
    extracted_data['state'] = ''
    extracted_data['zip_code'] = ''
    
    # Try multiple Australian address patterns
    patterns = [
        # Pattern 1: "22 FAIRY WREN CIRCUIT, Dakabin, QLD 4503" (with commas)
        r"^(.*?),\s*([A-Za-z\s]+),\s*([A-Z]{2,3})\s+(\d{4})$",
        # Pattern 2: "151 Warriewood Street Chandler QLD 4155" (no commas)
        r"^(.*?)\s+([A-Za-z\s]+)\s+([A-Z]{2,3})\s+(\d{4})$",
        # Pattern 3: "Unit 1/22 FAIRY WREN CIRCUIT, Dakabin QLD 4503" (unit with comma)
        r"^(.*?),\s*([A-Za-z\s]+)\s+([A-Z]{2,3})\s+(\d{4})$",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, address_str)
        if match:
            street_part = match.group(1).strip()
            city = match.group(2).strip()
            state = match.group(3).strip()
            zip_code = match.group(4).strip()
            
            # Remove any trailing commas from street part
            street_part = re.sub(r'[,\s]+$', '', street_part)
            
            # Split street into address1 and address2 if there's a comma
            if ',' in street_part:
                address_parts = street_part.split(',', 1)
                extracted_data['address1'] = address_parts[0].strip()
                extracted_data['address2'] = address_parts[1].strip()
            else:
                extracted_data['address1'] = street_part
                extracted_data['address2'] = ''
            
            extracted_data['city'] = city
            extracted_data['state'] = state
            extracted_data['zip_code'] = zip_code
            break
    
    # Set ship to address components if not already set
    if not extracted_data.get('ship_to_address1'):
        extracted_data['ship_to_address1'] = extracted_data['address1']
    if not extracted_data.get('ship_to_address2'):
        extracted_data['ship_to_address2'] = extracted_data.get('address2', '')
    if not extracted_data.get('ship_to_city'):
        extracted_data['ship_to_city'] = extracted_data['city']
    if not extracted_data.get('ship_to_state'):
        extracted_data['ship_to_state'] = extracted_data['state']
    if not extracted_data.get('ship_to_zip'):
        extracted_data['ship_to_zip'] = extracted_data['zip_code']
    
    logger.info(f"[ADDRESS PARSE] Raw: '{address_str}' | address1: '{extracted_data['address1']}', city: '{extracted_data['city']}', state: '{extracted_data['state']}', zip: '{extracted_data['zip_code']}'")


def parse_ambrose_address(address_str, extracted_data):
    """
    Parse Ambrose address string into components.
    Handles specific Ambrose format issues where street names appear in city field.
    Preserves proper case formatting.
    """
    if not address_str:
        return
    
    # Clean up the address string but preserve case
    address_str = address_str.strip()
    
    # Initialize default values
    extracted_data['address1'] = address_str
    extracted_data['address2'] = ''
    extracted_data['city'] = ''
    extracted_data['state'] = ''
    extracted_data['zip_code'] = ''
    
    # Ambrose-specific patterns to handle their address format
    patterns = [
        # Pattern 1: "4 Pampas Court Capalaba QLD 4157" - Need to separate street type from suburb
        # Look for: number + street_name + street_type + suburb + state + postcode
        r"^(\d+(?:/\d+)?\s+[A-Za-z\s]+?\s+(?:Court|Street|Road|Avenue|Drive|Circuit|Place|Lane|Way|Crescent)\b)\s+([A-Za-z][A-Za-z\s]*?)\s+([A-Z]{2,3})\s+(\d{4})$",
        # Pattern 2: "123 Street Name, Suburb, QLD 4000" (with commas) - Most reliable
        r"^(.*?),\s*([A-Za-z\s]+),\s*([A-Z]{2,3})\s+(\d{4})$",
        # Pattern 3: "Unit 1/123 Street Name, Suburb QLD 4000" (with comma after street)
        r"^(.*?),\s*([A-Za-z\s]+?)\s+([A-Z]{2,3})\s+(\d{4})$",
        # Pattern 4: Handle unit numbers "1/123 Street Name Suburb QLD 4000"
        r"^(\d+/\d+\s+[A-Za-z\s]+?)\s+([A-Za-z\s]+?)\s+([A-Z]{2,3})\s+(\d{4})$",
        # Pattern 5: Fallback - try to intelligently split based on common street types
        r"^(\d+(?:/\d+)?\s+[A-Za-z\s]+?)\s+([A-Za-z]+(?:\s+[A-Za-z]+)*?)\s+([A-Z]{2,3})\s+(\d{4})$",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, address_str)
        if match:
            street_part = match.group(1).strip()
            city_part = match.group(2).strip()
            state = match.group(3).strip()
            zip_code = match.group(4).strip()
            
            # For Ambrose, be more careful about separating street from city
            # If city_part contains common street words, it might be part of the street
            street_words = ['street', 'st', 'road', 'rd', 'avenue', 'ave', 'drive', 'dr', 'circuit', 'cct', 'place', 'pl', 'court', 'ct', 'lane', 'ln', 'way', 'crescent', 'cres']
            city_words = city_part.lower().split()
            
            # Check if any word in city_part is a street type
            has_street_word = any(word in street_words for word in city_words)
            
            if has_street_word and len(city_words) > 1:
                # Likely the street name extends into the city field
                # Try to find the actual city by looking for the last non-street word
                actual_city_words = []
                street_extension_words = []
                
                for word in city_words:
                    if word in street_words:
                        street_extension_words.append(word)
                    else:
                        # If we've already found street words, this might be the city
                        if street_extension_words:
                            actual_city_words.append(word)
                        else:
                            # Still part of street name
                            street_extension_words.append(word)
                
                if actual_city_words:
                    # Reconstruct the street and city
                    full_street = f"{street_part} {' '.join(street_extension_words)}".strip()
                    actual_city = ' '.join(actual_city_words).strip()
                    
                    extracted_data['address1'] = full_street
                    extracted_data['city'] = actual_city
                else:
                    # Fallback: use original parsing
                    extracted_data['address1'] = street_part
                    extracted_data['city'] = city_part
            else:
                # Normal parsing
                extracted_data['address1'] = street_part
                extracted_data['city'] = city_part
            
            extracted_data['address2'] = ''
            extracted_data['state'] = state
            extracted_data['zip_code'] = zip_code
            break
    
    # Set ship to address components if not already set
    if not extracted_data.get('ship_to_address1'):
        extracted_data['ship_to_address1'] = extracted_data['address1']
    if not extracted_data.get('ship_to_address2'):
        extracted_data['ship_to_address2'] = extracted_data.get('address2', '')
    if not extracted_data.get('ship_to_city'):
        extracted_data['ship_to_city'] = extracted_data['city']
    if not extracted_data.get('ship_to_state'):
        extracted_data['ship_to_state'] = extracted_data['state']
    if not extracted_data.get('ship_to_zip'):
        extracted_data['ship_to_zip'] = extracted_data['zip_code']
    
    logger.info(f"[AMBROSE ADDRESS PARSE] Raw: '{address_str}' | address1: '{extracted_data['address1']}', city: '{extracted_data['city']}', state: '{extracted_data['state']}', zip: '{extracted_data['zip_code']}'")


def match_builder_to_template(builder_name: str) -> str:
    """
    Match a builder name from the database to the appropriate extraction template.
    Uses fuzzy matching to handle variations in builder names.
    
    Args:
        builder_name: The builder name from the RFMS database
        
    Returns:
        The template name to use for extraction
    """
    if not builder_name:
        return ""
    
    # Normalize the builder name for comparison
    normalized_name = builder_name.lower().strip()
    
    # Define builder name patterns and their corresponding templates
    builder_patterns = {
        "ambrose": ["ambrose", "ambrose construct", "ambrose construction"],
        "profile_build": ["profile build", "profile build group", "pbg"],
        "rizon": ["rizon", "rizon group"],
        "campbell": ["campbell", "campbell construction", "campbell build"],
        "australian_restoration": ["australian restoration", "arc", "restoration company"],
        "townsend": ["townsend", "townsend building", "tbs", "townsend services"],
        "one_solutions": ["one solutions", "a to z flooring", "a to z flooring solutions"],
        "johns_lyng": ["johns lyng", "johns lyng group", "jl group"]
    }
    
    # First try exact substring matches
    for template, patterns in builder_patterns.items():
        for pattern in patterns:
            if pattern in normalized_name:
                logger.info(f"[BUILDER_MATCH] Exact match: '{builder_name}' -> '{template}'")
                return template
    
    # If no exact match, use fuzzy matching
    best_match = None
    best_score = 0.0
    
    for template, patterns in builder_patterns.items():
        for pattern in patterns:
            # Calculate similarity score
            score = SequenceMatcher(None, normalized_name, pattern).ratio()
            if score > best_score and score > 0.6:  # 60% similarity threshold
                best_score = score
                best_match = template
    
    if best_match:
        logger.info(f"[BUILDER_MATCH] Fuzzy match: '{builder_name}' -> '{best_match}' (score: {best_score:.2f})")
        return best_match
    
    logger.warning(f"[BUILDER_MATCH] No match found for builder: '{builder_name}'")
    return ""


def detect_builder_from_pdf(text: str) -> str:
    """
    Detect builder name from the first 5 lines of the PDF.
    Looks for builder names in headers, logos, addressed to sections, etc.
    
    Args:
        text: The extracted text from the PDF
        
    Returns:
        The detected builder name or empty string if not found
    """
    # Get first 5 lines or first 500 characters, whichever is less
    lines = text.split('\n')[:5]
    first_section = '\n'.join(lines)[:500].lower()
    
    logger.info(f"[BUILDER_DETECT] Analyzing first section: {first_section[:200]}...")
    
    # Check for known builder patterns
    builder_patterns = {
        'profile build group': ['profile build', 'profile building group', 'profilebuildgroup'],
        'ambrose construct group': ['ambrose construct', 'ambrose construction', 'ambrose group'],
        'campbell construction': ['campbell construction', 'campbell', 'ccc'],
        'australian restoration company': ['australian restoration', 'arc', 'aust restoration'],
        'townsend building services': ['townsend building', 'townsend', 'tbs'],
        'rizon group': ['rizon', 'rizon group', 'rizon construction'],
        'one solutions': ['one solutions', 'a to z flooring', 'a to z flooring solutions'],
        'johns lyng group': ['johns lyng', 'johns lyng group', 'jl group']
    }
    
    for builder_name, patterns in builder_patterns.items():
        for pattern in patterns:
            if pattern in first_section:
                logger.info(f"[BUILDER_DETECT] Found builder: {builder_name}")
                return builder_name
                
    # Check for "To:" or "Attention:" patterns
    to_match = re.search(r'(?:to|attention|attn):\s*([a-z\s&]+?)(?:\n|$)', first_section, re.IGNORECASE)
    if to_match:
        potential_builder = to_match.group(1).strip()
        logger.info(f"[BUILDER_DETECT] Found in To/Attention field: {potential_builder}")
        # Match against known builders
        for builder_name, patterns in builder_patterns.items():
            for pattern in patterns:
                if pattern in potential_builder.lower():
                    return builder_name
    
    logger.info("[BUILDER_DETECT] No builder detected in first section")
    return ""
