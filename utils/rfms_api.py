import requests
import logging
import json
import os
import base64
from datetime import datetime, timedelta
from requests.exceptions import RequestException, Timeout, ConnectionError
from models import db, RFMSSession
import http.client
import time
from functools import lru_cache

logger = logging.getLogger(__name__)


class RfmsApi:
    """
    Client for interacting with the RFMS API v2.

    This class handles authentication and provides methods for various API endpoints.
    """

    def __init__(self, base_url, store_code, username, api_key):
        """
        Initialize the RFMS API client.

        Args:
            base_url (str): The base URL for the RFMS API
            store_code (str): The store code for authentication
            username (str): The username for authentication
            api_key (str): The API key for authentication
        """
        self.base_url = base_url
        self.store_code = store_code
        self.username = username
        self.api_key = api_key
        self.session_token = None
        self.session_expiry = None
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.timeout = 10
        self.max_retries = 2
        self.auth = None  # Will store the current auth tuple

        # Validate required credentials
        self._validate_credentials()

    def _validate_credentials(self):
        """Validate that all required credentials are present."""
        missing = []
        if not self.store_code:
            missing.append("store_code")
        if not self.api_key:
            missing.append("api_key")
        
        if missing:
            raise ValueError(f"Missing required RFMS API credentials: {', '.join(missing)}. "
                           f"Please check your environment variables.")

    def _get_auth(self, for_handshake=False):
        # Ensure credentials are still valid
        if not self.store_code or not self.api_key:
            raise ValueError("RFMS API credentials are not properly configured")
            
        if for_handshake:
            return (self.store_code, self.api_key)
        else:
            if not self.session_token:
                raise ValueError("Session token is not available. Please ensure session is established.")
            return (self.store_code, self.session_token)

    def _get_headers(self, extra_headers=None, include_session=False):
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def get_stored_session(self):
        session_row = RFMSSession.query.first()
        if session_row:
            return session_row.token, session_row.expiry
        return None, None

    def store_session(self, token, expiry):
        session_row = RFMSSession.query.first()
        if session_row:
            session_row.token = token
            session_row.expiry = expiry
        else:
            session_row = RFMSSession(token=token, expiry=expiry)
            db.session.add(session_row)
        db.session.commit()

    def ensure_session(self):
        now = datetime.utcnow()
        skew = timedelta(seconds=10)
        token, expiry = self.get_stored_session()
        logger.debug(f"[SESSION] ensure_session: now (UTC)={now} ({type(now)}), expiry={expiry} ({type(expiry)})")
        # If expiry is a string, try to parse it as UTC
        if expiry and not isinstance(expiry, datetime):
            try:
                expiry = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
                logger.debug(f"[SESSION] Parsed expiry from string as UTC: {expiry}")
            except Exception as e:
                logger.warning(f"[SESSION] Could not parse expiry: {expiry}, error: {e}")
                expiry = None
        if token and expiry and now < expiry - skew:
            logger.info(f"[SESSION] Reusing existing session token: {token}, expiry: {expiry} (UTC), now: {now} (UTC)")
            self.session_token = token
            self.session_expiry = expiry
            return True
        logger.info(f"[SESSION] Session token missing or expired. Previous token: {token}, expiry: {expiry}, now: {now}. Triggering handshake.")
        token, expiry = self.get_session()
        if token and expiry:
            self.session_token = token
            self.session_expiry = expiry
            self.store_session(token, expiry)
            return True
        return False

    def get_session(self):
        """
        Get a new session token from the RFMS API using Basic Auth.
        Returns:
            tuple: (token, expiry) if successful, (None, None) otherwise
        """
        url = f"{self.base_url}/v2/Session/Begin"
        headers = self._get_headers(include_session=False)
        auth = self._get_auth(for_handshake=True)
        logger.debug(f"[SESSION] get_session called. Current token: {self.session_token}, expiry: {self.session_expiry}, now: {datetime.now()}")
        try:
            logger.info(f"Attempting to begin session at {url} with store code {self.store_code}")
            logger.debug(f"[RFMS API] Outgoing handshake auth: (username: {auth[0]}, password: {'*' * len(auth[1])})")
            logger.debug(f"[RFMS API] Outgoing headers: {headers}")
            response = requests.post(
                url, headers=headers, auth=auth, timeout=self.timeout
            )
            logger.info(f"RFMS API response status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"[SESSION] Session response data: {data}")
                token = data.get("sessionToken")
                expiry = None
                if not token:
                    logger.error(f"Session begin succeeded but no sessionToken in response: {data}")
                    return None, None
                if "sessionExpires" in data:
                    logger.debug(f"[SESSION] sessionExpires from API: {data['sessionExpires']}")
                    try:
                        expiry = datetime.strptime(
                            data["sessionExpires"], "%a, %d %b %Y %H:%M:%S GMT"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to parse sessionExpires: {data.get('sessionExpires')}, error: {e}")
                        expiry = None
                if not expiry:
                    expiry = datetime.now() + timedelta(minutes=15)
                    logger.debug(f"[SESSION] Fallback session_expiry set to: {expiry}")
                logger.info(f"Successfully obtained RFMS API session token: {token}, expires at: {expiry}")
                return token, expiry
            else:
                logger.error(f"Session begin failed: {response.status_code} {response.text}")
                return None, None
        except Exception as e:
            logger.error(f"Error getting RFMS API session: {str(e)}")
            return None, None

    def execute_request(self, method, url, payload=None, retry_count=0):
        """
        Execute an API request with retry logic and error handling.

        Args:
            method (str): HTTP method (GET, POST, PUT, DELETE)
            url (str): Request URL
            payload (dict): Request payload (for POST/PUT)
            retry_count (int): Current retry count

        Returns:
            dict: Response data if successful

        Raises:
            Exception: If request fails after all retries
        """
        logger.info(f"[RFMS API] {method} {url} | Payload: {payload}")
        if not self.ensure_session():
            raise Exception("Failed to establish RFMS API session")
        headers = self._get_headers()
        auth = self._get_auth()
        logger.debug(
            f"[RFMS API] Outgoing auth: (username: {auth[0]}, password: {'*' * len(str(auth[1]))})"
        )
        logger.debug(f"[RFMS API] Outgoing headers: {headers}")
        try:
            logger.debug(f"Executing {method} request to {url}")

            if method.upper() == "GET":
                response = requests.get(
                    url, headers=headers, auth=auth, timeout=self.timeout
                )
            elif method.upper() == "POST":
                response = requests.post(
                    url, headers=headers, auth=auth, json=payload, timeout=self.timeout
                )
            elif method.upper() == "PUT":
                response = requests.put(
                    url, headers=headers, auth=auth, json=payload, timeout=self.timeout
                )
            elif method.upper() == "DELETE":
                response = requests.delete(
                    url, headers=headers, auth=auth, timeout=self.timeout
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Check for successful response
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON response from {url}")
                    raise Exception("Invalid JSON response from API")

            # Handle unauthorized response (401) by getting a new session and retrying
            elif response.status_code == 401 and retry_count < self.max_retries:
                logger.warning(
                    "Session expired or unauthorized, requesting new session"
                )
                self.session_token = None
                self.session_expiry = None
                return self.execute_request(method, url, payload, retry_count + 1)

            # Handle other errors
            else:
                error_message = f"API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_message += f": {error_data['error']}"
                except:
                    error_message += f": {response.text}"

                logger.error(error_message)
                raise Exception(error_message)

        except Exception as e:
            logger.error(f"Error executing request: {str(e)}")
            raise

    def check_status(self):
        """
        Check if the RFMS API is available.
        Returns:
            str: 'online' if API is available, 'offline' otherwise
        """
        url = f"{self.base_url}/v2/Session/Begin"
        try:
            headers = self._get_headers(include_session=False)
            auth = self._get_auth(for_handshake=True)
            logger.debug(
                f"[RFMS API] Outgoing handshake auth: (username: {auth[0]}, password: {'*' * len(str(auth[1]))})"
            )
            logger.debug(f"[RFMS API] Outgoing headers: {headers}")
            response = requests.post(
                url, headers=headers, auth=auth, timeout=self.timeout
            )
            if response.status_code == 200:
                return "online"
            else:
                logger.warning(
                    f"API connection failed with status code: {response.status_code}"
                )
                return "offline"
        except Timeout:
            logger.error("API status check timed out")
            return "offline"
        except ConnectionError:
            logger.error("API connection error during status check")
            return "offline"
        except Exception as e:
            logger.error(f"Error checking API status: {str(e)}")
            return "offline"

    def find_customers(self, search_term, page=0, include_inactive=True):
        logger.info(f"Finding customers with search term: {search_term}, include_inactive=True")
        self.ensure_session()
        # Extract host from base_url
        host = self.base_url.replace("https://", "").replace("http://", "").split("/")[0]
        conn = http.client.HTTPSConnection(host)
        payload_dict = {
            "searchText": search_term,
            "includeCustomers": True,
            "includeProspects": False,
            "includeInactive": True,
            "customerSource": "Customer",
            "referralType": "Standalone"
        }
        if page > 0:
            payload_dict["startIndex"] = page * 10
        payload = json.dumps(payload_dict)
        headers = {
            'Content-Type': 'application/json'
        }
        conn.request("POST", "/v2/customers/find", payload, headers)
        res = conn.getresponse()
        data = res.read()
        try:
            result = json.loads(data.decode("utf-8"))
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                for key in ["customers", "result", "data"]:
                    if key in result:
                        return result[key]
            return []
        except Exception as e:
            logger.error(f"Error parsing customer search response: {e}")
            return []

    def probe_customers_endpoint(self, search_term):
        self.ensure_session()
        url = f"{self.base_url}/v2/customers"
        payload = {"searchText": search_term}
        try:
            headers = self._get_headers()
            auth = self._get_auth()
            logger.debug(
                f"[RFMS API] Outgoing auth: (username: {auth[0]}, password: {'*' * len(str(auth[1]))})"
            )
            logger.debug(f"[RFMS API] Outgoing headers: {headers}")
            response = requests.post(
                url, headers=headers, auth=auth, json=payload, timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Error probing /v2/customers: {response.text}")
                return response.text
        except Exception as e:
            logger.error(f"Error probing /v2/customers: {str(e)}")
            return str(e)

    def find_customer_by_id(self, customer_id):
        start_time = time.monotonic()
        logger.info(f"[TIMER] find_customer_by_id started")
        """
        Find a customer by ID using the customer endpoint.
        Args:
            customer_id (str): The customer ID to search for
        Returns:
            list: List containing the customer object if found
        """
        url = f"{self.base_url}/v2/customer/{customer_id}"
        try:
            logger.info(f"Finding customer by ID: {customer_id}")
            api_start = time.monotonic()
            data = self.execute_request("GET", url)
            api_end = time.monotonic()
            logger.info(f"[TIMER] API call duration: {api_end - api_start:.2f}s")
            logger.info(f"[RAW API RESPONSE] /v2/customer/{{customer_id}}: {data}")
            if not data or "result" not in data:
                logger.warning(f"No customer found with ID: {customer_id}")
                return []
            result = data.get("result", {})
            detail = data.get("detail", {})
            customer_address = result.get("customerAddress", {})

            # Helper to pick the first non-empty field
            def pick_any_field(*fields):
                for f in fields:
                    if f and isinstance(f, str) and f.strip():
                        return f.strip()
                return ""

            # Helper to check for valid address
            def is_po_box(addr):
                return addr and isinstance(addr, str) and 'po box' in addr.lower()
            def is_street(addr):
                if not addr or not isinstance(addr, str):
                    return False
                lower = addr.lower()
                # Exclude ABN and other non-address markers
                if 'abn:' in lower or 'gst:' in lower or 'tax' in lower:
                    return False
                # Heuristic: must contain a number or 'unit' or 'suite' or 'lot' or 'street' or 'road' or 'ave' or 'drive' or 'blvd' or 'lane'
                keywords = ['unit', 'suite', 'lot', 'street', 'st', 'road', 'rd', 'ave', 'avenue', 'drive', 'dr', 'blvd', 'lane']
                if any(k in lower for k in keywords) or any(c.isdigit() for c in addr):
                    return True
                return False

            def pick_address_fields(addr1, addr2, extra=None):
                addr1 = addr1.strip() if addr1 else ''
                addr2 = addr2.strip() if addr2 else ''
                extra = extra.strip() if extra else ''
                # Prefer valid street or PO Box, skip ABN
                if is_street(addr1):
                    return addr1, addr2 if addr2 else extra
                if is_po_box(addr1):
                    return addr1, addr2 if addr2 else extra
                if is_street(addr2):
                    return addr2, extra
                if is_po_box(addr2):
                    return addr2, extra
                if is_street(extra):
                    return extra, ''
                if is_po_box(extra):
                    return extra, ''
                return '', ''

            address1, address2 = pick_address_fields(
                customer_address.get("address1"),
                customer_address.get("address2"),
                detail.get("customerAddress2")
            )
            # Validation: reject if both are empty
            if not address1:
                logger.warning("No valid address found for customer; rejecting address fields.")
                address1 = address2 = ''

            city = pick_any_field(
                customer_address.get("city"),
                detail.get("customerCity"),
            )
            state = pick_any_field(
                customer_address.get("state"),
                detail.get("customerState"),
            )
            zip_code = pick_any_field(
                customer_address.get("postalCode"),
                detail.get("customerZIP"),
            )
            # Phone extraction: check all possible fields in order
            phone = pick_any_field(
                detail.get("customerPhone"),
                detail.get("customerPhone2"),
                detail.get("customerPhone3"),
                result.get("phone1"),
                result.get("phone2"),
                result.get("phone3"),
                customer_address.get("phone"),
            )
            # Email extraction: check all possible fields in order
            email = pick_any_field(
                detail.get("customerEmail"),
                result.get("email"),
                customer_address.get("email"),
            )
            use_sold_to_business_name = detail.get("useSoldToBusinessName", False)
            formatted_customer = {
                "id": result.get("customerId") or detail.get("customerSourceId"),
                "customer_source_id": result.get("customerId") or detail.get("customerSourceId"),
                "name": pick_any_field(
                    detail.get("customerName"), customer_address.get("businessName")
                ),
                "first_name": pick_any_field(
                    detail.get("customerFirstName"), customer_address.get("firstName")
                ),
                "last_name": pick_any_field(
                    detail.get("customerLastName"), customer_address.get("lastName")
                ),
                "business_name": pick_any_field(
                    customer_address.get("businessName"),
                    detail.get("customerBusinessName"),
                ),
                "address": f"{address1}, {city}, {state} {zip_code}",
                "address1": address1,
                "address2": address2,
                "city": city,
                "state": state,
                "zip_code": zip_code,
                "email": email,
                "phone": phone,
                "use_sold_to_business_name": use_sold_to_business_name,
                "internal_notes": detail.get("internalNotes", ""),
                "customer_type": result.get(
                    "customerType", detail.get("customerType", "")
                ),
                "preferred_salesperson1": result.get(
                    "preferredSalesperson1", detail.get("preferredSalesperson1", "")
                ),
                "preferred_salesperson2": result.get(
                    "preferredSalesperson2", detail.get("preferredSalesperson2", "")
                ),
                "store_number": result.get(
                    "storeNumber", detail.get("defaultStore", "")
                ),
            }
            end_time = time.monotonic()
            logger.info(f"[TIMER] find_customer_by_id total duration: {end_time - start_time:.2f}s")
            return [formatted_customer]
        except Exception as e:
            logger.error(f"Error finding customer by ID: {str(e)}")
            logger.info(f"[TIMER] find_customer_by_id errored after {time.monotonic() - start_time:.2f}s")
            return []

    @lru_cache(maxsize=32)
    def _cached_find_customer_by_name(self, name, start_index):
        logger.info(f"[CACHE] Miss for ({name}, {start_index})")
        return self._find_customer_by_name_uncached(name, start_index)

    def _find_customer_by_name_uncached(self, name, start_index):
        # This is the original logic from find_customer_by_name, minus logging and timing
        self.ensure_session()
        payload = {
            "searchText": name,
            "includeCustomers": True,
            "includeInactive": True,
            "storeNumber": "1"
        }
        if start_index > 0:
            payload["startIndex"] = start_index
        url = f"{self.base_url}/v2/customers/find"
        data = self.execute_request("POST", url, payload)
        if isinstance(data, dict) and "detail" in data and data["detail"]:
            return data["detail"]
        for key in ["customers", "result", "data"]:
            if key in data and data[key]:
                return data[key]
        return []

    def find_customer_by_name(self, name, include_inactive=True, start_index=0):
        start_time = time.monotonic()
        logger.info(f"[TIMER] find_customer_by_name started")
        # Use the cache
        try:
            result = self._cached_find_customer_by_name(name, start_index)
            logger.info(f"[CACHE] Hit for ({name}, {start_index})")
        except Exception as e:
            logger.error(f"[CACHE] Error: {e}")
            result = self._find_customer_by_name_uncached(name, start_index)
        end_time = time.monotonic()
        logger.info(f"[TIMER] find_customer_by_name total duration: {end_time - start_time:.2f}s")
        return result

    def get_customer(self, customer_id):
        """
        Get a customer by ID using the RFMS API.
        Uses GET request with store code and session token authentication.

        Args:
            customer_id (str): The customer ID to retrieve

        Returns:
            dict: Customer object if found, None otherwise
        """
        logger.info(f"Getting customer with ID: {customer_id}")
        url = f"{self.base_url}/v2/customer/{customer_id}"
        try:
            if not self.ensure_session():
                logger.error("Failed to establish session for customer retrieval")
                return None
            headers = self._get_headers()
            auth = self._get_auth()
            logger.debug(
                f"[RFMS API] Outgoing auth: (username: {auth[0]}, password: {'*' * len(str(auth[1]))})"
            )
            logger.debug(f"[RFMS API] Outgoing headers: {headers}")
            response = requests.get(
                url, headers=headers, auth=auth, timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                if "result" in data:
                    customer = data.get("result", {})
                    logger.info(
                        f"Successfully retrieved customer: {customer.get('customerId', '')}"
                    )
                    return self._format_customer(customer)
                else:
                    logger.warning(f"No customer found with ID: {customer_id}")
                    return None
            else:
                logger.error(
                    f"Failed to get customer. Status code: {response.status_code}"
                )
                logger.error(f"Response: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting customer {customer_id}: {str(e)}")
            raise Exception(f"Error getting customer {customer_id}: {str(e)}")

    def create_customer(self, customer_data):
        """
        Create a new customer in RFMS.

        Args:
            customer_data (dict): Customer data

        Returns:
            dict: Created customer object
        """
        url = f"{self.base_url}/v2/customer"
        
        # Validate required fields
        required_fields = ['customerType', 'entryType', 'customerAddress']
        missing_fields = [field for field in required_fields if field not in customer_data]
        
        if missing_fields:
            raise ValueError(f"Missing required customer data: {', '.join(missing_fields)}")
        
        try:
            data = self.execute_request('POST', url, customer_data)
            logger.info(f"[CREATE_CUSTOMER] Raw RFMS response: {json.dumps(data, indent=2)}")
            return data
        except Exception as e:
            logger.error(f"Error creating customer: {str(e)}")
            raise Exception(f"Error creating customer: {str(e)}")

    def create_quote(self, quote_data):
        """
        Create a new quote in RFMS.

        Args:
            quote_data (dict): Quote data

        Returns:
            dict: Created quote object
        """
        customer_id = quote_data.get('customer_id')
        logger.info(f"[RFMS_API][CREATE_QUOTE] Using customer ID: {customer_id}")
        if not customer_id:
            raise ValueError("Missing customer_id in quote_data")
        url = f"{self.base_url}/api/v2/Quote"
        payload = {
            "quote": {
                "customerId": quote_data.get("customer_id"),
                "opportunityName": quote_data.get(
                    "opportunity_name", "New Opportunity"
                ),
                "storeCode": self.store_code,
                "salesPerson": quote_data.get("sales_person", ""),
                "workOrderNotes": quote_data.get("scope_of_work", ""),
                "billToAddress": {
                    "name": quote_data.get("bill_to_name", ""),
                    "address1": quote_data.get("bill_to_address1", ""),
                    "address2": quote_data.get("bill_to_address2", ""),
                    "city": quote_data.get("bill_to_city", ""),
                    "state": quote_data.get("bill_to_state", ""),
                    "postalCode": quote_data.get("bill_to_zip", ""),
                    "country": quote_data.get("bill_to_country", "Australia"),
                },
                "shipToAddress": {
                    "name": quote_data.get("ship_to_name", ""),
                    "address1": quote_data.get("ship_to_address1", ""),
                    "address2": quote_data.get("ship_to_address2", ""),
                    "city": quote_data.get("ship_to_city", ""),
                    "state": quote_data.get("ship_to_state", ""),
                    "postalCode": quote_data.get("ship_to_zip", ""),
                    "country": quote_data.get("ship_to_country", "Australia"),
                },
            }
        }
        try:
            headers = self._get_headers()
            auth = self._get_auth()
            logger.debug(
                f"[RFMS API] Outgoing auth: (username: {auth[0]}, password: {'*' * len(str(auth[1]))})"
            )
            logger.debug(f"[RFMS API] Outgoing headers: {headers}")
            response = requests.post(
                url, headers=headers, auth=auth, json=payload, timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("result", {}).get("quote", {})
            else:
                logger.error(f"Error creating quote: {response.text}")
                raise Exception(f"Error creating quote: {response.text}")
        except Exception as e:
            logger.error(f"Error creating quote: {str(e)}")
            raise Exception(f"Error creating quote: {str(e)}")

    def create_job(self, job_data):
        """
        Create a new job in RFMS using comprehensive format.
        Handles both new comprehensive format and legacy nested format.

        Args:
            job_data (dict): Job data - supports both formats:
                            - Comprehensive: flat structure with soldTo/shipTo
                            - Legacy: nested under 'order' key

        Returns:
            dict: Created job object
        """
        try:
            # Handle both comprehensive format and legacy nested format
            if 'order' in job_data:
                # Legacy nested format
                customer_id = job_data['order'].get('CustomerSeqNum')
                logger.info(f"[RFMS_API][CREATE_JOB] Using legacy nested format - Customer ID: {customer_id}")
                payload = job_data  # Use as-is for legacy
            else:
                # New comprehensive format
                customer_id = None
                if 'soldTo' in job_data and isinstance(job_data['soldTo'], dict):
                    customer_id = job_data['soldTo'].get('customerId')
                logger.info(f"[RFMS_API][CREATE_JOB] Using comprehensive format - Customer ID: {customer_id}")
                payload = job_data  # Use as-is for comprehensive format
            
            if not customer_id:
                raise ValueError("Missing customer ID in job data")
            
            session_token = self.session_token
            if not session_token:
                raise Exception("Failed to get session token")
            
            headers = self._get_headers()
            auth = self._get_auth()
            
            logger.debug(f"[RFMS API] Outgoing auth: (username: {auth[0]}, password: {'*' * len(str(auth[1]))})")
            logger.debug(f"[RFMS API] Outgoing headers: {headers}")
            logger.info(f"[RFMS API] Payload format: {'comprehensive' if 'soldTo' in job_data else 'legacy'}")
            
            response = requests.post(
                f"{self.base_url}/v2/order/create", 
                headers=headers, 
                auth=auth, 
                json=payload
            )
            
            logger.info(f"[RFMS API] Order creation response status: {response.status_code}")
            logger.info(f"[RFMS API] Order creation response body: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[RFMS API] Parsed response JSON: {result}")
                if result.get("status") == "success":
                    order_id = result.get("result")
                    logger.info(f"[RFMS API] Successfully created order: {order_id}")
                    return result
                else:
                    logger.error(f"[RFMS API] Error response structure: {result}")
                    error_msg = result.get('result', result.get('message', result.get('error', 'Unknown error')))
                    raise Exception(f"RFMS API returned error: {error_msg}")
            else:
                raise Exception(f"Failed to create job - HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"Error creating job: {str(e)}")
            raise

    def add_to_billing_group(self, order_ids):
        """
        Add orders to a billing group.

        Args:
            order_ids (list): List of order IDs to add to a billing group

        Returns:
            dict: Result of the operation
        """
        url = f"{self.base_url}/api/v2/BillingGroup"
        if not order_ids or not isinstance(order_ids, list) or len(order_ids) < 1:
            raise ValueError("At least one order ID is required")
        payload = {"orderIds": order_ids}
        try:
            headers = self._get_headers()
            auth = self._get_auth()
            logger.debug(
                f"[RFMS API] Outgoing auth: (username: {auth[0]}, password: {'*' * len(str(auth[1]))})"
            )
            logger.debug(f"[RFMS API] Outgoing headers: {headers}")
            response = requests.post(
                url, headers=headers, auth=auth, json=payload, timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("result", {})
            else:
                logger.error(f"Error adding orders to billing group: {response.text}")
                raise Exception(
                    f"Error adding orders to billing group: {response.text}"
                )
        except Exception as e:
            logger.error(f"Error adding orders to billing group: {str(e)}")
            raise Exception(f"Error adding orders to billing group: {str(e)}")

    def find_customers_advanced(self, search_params):
        url = f"{self.base_url}/v2/customers/find"
        try:
            headers = self._get_headers()
            auth = self._get_auth()
            logger.debug(
                f"[RFMS API] Outgoing auth: (username: {auth[0]}, password: {'*' * len(str(auth[1]))})"
            )
            logger.debug(f"[RFMS API] Outgoing headers: {headers}")
            # Remove 'stores' key if present
            if 'stores' in search_params:
                del search_params['stores']
            response = requests.post(
                url,
                headers=headers,
                auth=auth,
                json=search_params,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return response.json().get("result", {})
            else:
                logger.error(f"Error in advanced customer search: {response.text}")
                return {}
        except Exception as e:
            logger.error(f"Error in advanced customer search: {str(e)}")
            return {}

    def get_customer_values(self):
        url = f"{self.base_url}/v2/customer/values"
        try:
            headers = self._get_headers()
            auth = self._get_auth()
            logger.debug(
                f"[RFMS API] Outgoing auth: (username: {auth[0]}, password: {'*' * len(str(auth[1]))})"
            )
            logger.debug(f"[RFMS API] Outgoing headers: {headers}")
            response = requests.get(
                url, headers=headers, auth=auth, timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json().get("result", {})
            else:
                logger.error(f"Error getting customer values: {response.text}")
                return {}
        except Exception as e:
            logger.error(f"Error getting customer values: {str(e)}")
            return {}

    def _format_customer_list(self, customers):
        start_time = time.monotonic()
        logger.info(f"[TIMER] _format_customer_list started")
        formatted_customers = []
        for customer in customers:
            if not isinstance(customer, dict):
                continue
            # If 'detail' key exists, merge it for field extraction
            detail = customer.get("detail", {}) if isinstance(customer.get("detail", {}), dict) else {}
            def pick_any_field(*fields):
                for f in fields:
                    if f and isinstance(f, str) and f.strip():
                        return f.strip()
                return ""
            customer_source_id = (
                customer.get("customerSourceId") or customer.get("customerId") or detail.get("customerSourceId") or detail.get("customerId")
            )
            name = pick_any_field(
                customer.get("customerName"),
                customer.get("customerBusinessName"),
                customer.get("shipToName"),
                customer.get("shipToBusinessName"),
                detail.get("customerName"),
                detail.get("customerBusinessName"),
                detail.get("shipToName"),
                detail.get("shipToBusinessName"),
            )
            first_name = pick_any_field(
                customer.get("customerFirstName"),
                customer.get("shipToFirstName"),
                detail.get("customerFirstName"),
                detail.get("shipToFirstName"),
            )
            last_name = pick_any_field(
                customer.get("customerLastName"),
                customer.get("shipToLastName"),
                name,
                detail.get("customerLastName"),
                detail.get("shipToLastName"),
            )
            business_name = pick_any_field(
                customer.get("customerBusinessName"),
                customer.get("shipToBusinessName"),
                detail.get("customerBusinessName"),
                detail.get("shipToBusinessName"),
            )
            address = pick_any_field(
                customer.get("customerAddress"),
                customer.get("shipToAddress"),
                detail.get("customerAddress"),
                detail.get("shipToAddress"),
            )
            address1 = pick_any_field(
                customer.get("customerAddress"),
                customer.get("customerAddress1"),
                customer.get("shipToAddress"),
                customer.get("shipToAddress1"),
                detail.get("customerAddress"),
                detail.get("customerAddress1"),
                detail.get("shipToAddress"),
                detail.get("shipToAddress1"),
            )
            address2 = pick_any_field(
                customer.get("customerAddress2"),
                customer.get("shipToAddress2"),
                detail.get("customerAddress2"),
                detail.get("shipToAddress2"),
            )
            city = pick_any_field(
                customer.get("customerCity"),
                customer.get("shipToCity"),
                detail.get("customerCity"),
                detail.get("shipToCity"),
            )
            state = pick_any_field(
                customer.get("customerState"),
                customer.get("shipToState"),
                detail.get("customerState"),
                detail.get("shipToState"),
            )
            zip_code = pick_any_field(
                customer.get("customerZIP"),
                customer.get("shipToZIP"),
                detail.get("customerZIP"),
                detail.get("shipToZIP"),
            )
            country = pick_any_field(
                customer.get("customerCountry"),
                customer.get("shipToCountry"),
                detail.get("customerCountry"),
                detail.get("shipToCountry"),
            )
            phone = pick_any_field(
                customer.get("customerPhone"),
                customer.get("shipToPhone"),
                customer.get("customerPhone1"),
                customer.get("customerPhone2"),
                customer.get("customerPhone3"),
                detail.get("customerPhone"),
                detail.get("shipToPhone"),
                detail.get("customerPhone1"),
                detail.get("customerPhone2"),
                detail.get("customerPhone3"),
            )
            email = pick_any_field(
                customer.get("customerEmail"),
                customer.get("shipToEmail"),
                detail.get("customerEmail"),
                detail.get("shipToEmail"),
            )
            use_sold_to_business_name = customer.get("useSoldToBusinessName", False) or detail.get("useSoldToBusinessName", False)
            # Improved logging for customer source ID and missing fields
            logger.warning(f"[DEBUG] Raw customer dict: {customer}")
            logger.info(f"[CUSTOMER_FORMAT] customerSourceId: {customer_source_id}, name: {name}, first_name: {first_name}, last_name: {last_name}, business_name: {business_name}, address1: {address1}, city: {city}, state: {state}, zip: {zip_code}")
            missing_fields = [
                k for k, v in {
                    'id': customer_source_id,
                    'name': name,
                    'first_name': first_name,
                    'last_name': last_name,
                    'address1': address1,
                    'city': city,
                    'state': state,
                    'zip_code': zip_code
                }.items() if not v
            ]
            if missing_fields:
                logger.warning(f"[CUSTOMER_FORMAT] Missing fields for customerSourceId {customer_source_id}: {missing_fields}")
            formatted_customer = {
                "id": customer_source_id,
                "customer_source_id": customer_source_id,
                "name": name,
                "first_name": first_name,
                "last_name": last_name,
                "business_name": business_name,
                "address": address,
                "address1": address1,
                "address2": address2,
                "city": city,
                "state": state,
                "zip_code": zip_code,
                "country": country,
                "phone": phone,
                "email": email,
                "use_sold_to_business_name": use_sold_to_business_name,
            }
            logger.warning(f"[DEBUG] Formatted customer: {formatted_customer}")
            formatted_customers.append(formatted_customer)
        end_time = time.monotonic()
        logger.info(f"[TIMER] _format_customer_list duration: {end_time - start_time:.2f}s for {len(formatted_customers)} customers")
        return formatted_customers

    def find_order_by_po_number(self, po_number):
        """
        Search for an order in RFMS by PO number.
        Returns the order if found, or None if not found.
        """
        url = f"{self.base_url}/v2/order/find"
        payload = {"poNumber": po_number}
        headers = self._get_headers()
        auth = self._get_auth()
        try:
            response = requests.post(url, headers=headers, auth=auth, json=payload, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                if data.get("result"):
                    logger.info(f"Order found for PO number {po_number}: {data['result']}")
                    return data["result"]
                logger.info(f"No order found for PO number {po_number}.")
                return None
            else:
                logger.error(f"Order find failed: {response.status_code} {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error searching for order by PO number: {str(e)}")
            return None
