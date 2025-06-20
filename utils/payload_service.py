# utils/payload_service.py
import os
import json
from datetime import datetime, timedelta

# Define custom exception for payload errors if needed
class PayloadError(ValueError):
    pass

def _get_first_name(data, default_first="Unknown"):
    """Extract first name from data with robust fallbacks"""
    # Try explicit first_name field first
    if data.get("first_name"):
        return data["first_name"].strip()
    
    # Try splitting name field
    name = data.get("name", "").strip()
    if name:
        parts = name.split()
        if parts:
            return parts[0]
    
    # Return default
    return default_first

def _get_last_name(data, default_last=""):
    """Extract last name from data with robust fallbacks"""
    # Try explicit last_name field first
    if data.get("last_name"):
        return data["last_name"].strip()
    
    # Try splitting name field
    name = data.get("name", "").strip()
    if name:
        parts = name.split()
        if len(parts) > 1:
            return " ".join(parts[1:])
        elif len(parts) == 1 and not data.get("first_name"):
            # If we only have one name part and no explicit first_name, use it as last_name
            return parts[0]
    
    # Return default
    return default_last

def build_rfms_customer_payload(data):
    """
    Builds the payload for creating a new customer in RFMS.
    This creates a customer-specific payload, not an order payload.
    """
    if data is None:
        raise PayloadError("No data provided for customer creation")

    # Required fields validation - check multiple possible locations for first/last names
    first_name = (
        data.get("first_name", "") or 
        data.get("customer", {}).get("first_name", "") or 
        data.get("ship_to", {}).get("first_name", "")
    )
    last_name = (
        data.get("last_name", "") or 
        data.get("customer", {}).get("last_name", "") or 
        data.get("ship_to", {}).get("last_name", "")
    )
    
    # If still no names, try to split customer_name from PDF extraction
    if not first_name or not last_name:
        customer_name = data.get("customer_name", "")
        if customer_name:
            name_parts = customer_name.split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = " ".join(name_parts[1:])
            else:
                first_name = ""
                last_name = customer_name
    
    if not first_name or not last_name:
        raise PayloadError("Customer first name and last name are required.")

    # Build customer-specific payload matching RFMS API documentation exactly
    payload = {
        "customerType": "INSURANCE",  # Required by RFMS for customer creation
        "entryType": "Customer",  # Required by RFMS for customer creation (from API docs)
        "customerAddress": {
            "lastName": last_name,
            "firstName": first_name,
            "address1": data.get("address1", ""),
            "address2": data.get("address2", ""),
            "city": data.get("city", ""),
            "state": data.get("state", ""),
            "postalCode": data.get("zip_code", ""),
            "county": ""  # Optional field from API docs
        },
        "shipToAddress": {
            "lastName": last_name,
            "firstName": first_name,
            "address1": data.get("address1", ""),
            "address2": data.get("address2", ""),
            "city": data.get("city", ""),
            "state": data.get("state", ""),
            "postalCode": data.get("zip_code", ""),
            "county": ""  # Optional field from API docs
        },
        "phone1": data.get("phone", ""),
        "phone2": data.get("phone2", ""),
        "email": data.get("email", ""),
        "taxStatus": "Tax",  # From API docs
        "taxMethod": "SalesTax",  # From API docs
        "preferredSalesperson1": "ZORAN VEKIC",
        "preferredSalesperson2": "",
        "storeNumber": "49"
    }
    return payload

def build_rfms_order_payload(export_data, logger=None):
    """
    Builds the RFMS order payload using the proven AZ002874 method.
    This implementation uses the flat structure that creates populated orders in the regular orders section.
    """
    if not export_data:
        raise PayloadError("No export data provided")

    # Extract main data sections
    sold_to_data = export_data.get("sold_to", {})
    ship_to_data = export_data.get("ship_to", {})
    job_details_data = export_data.get("job_details", {})
    
    # Extract customer name from PDF extraction (from "Insured Owner" field) for ship to details
    # Check multiple possible locations for the customer name
    extracted_customer_name = (
        job_details_data.get("customer_name") or 
        export_data.get("customer_name", "") or
        ship_to_data.get("name", "") or
        ship_to_data.get("customer_name", "")
    )
    if logger:
        logger.info(f"[SHIP_TO_CUSTOMER] Extracted customer name from PDF: '{extracted_customer_name}'")
        logger.info(f"[SHIP_TO_CUSTOMER] Available sources - job_details.customer_name: '{job_details_data.get('customer_name', 'N/A')}', export_data.customer_name: '{export_data.get('customer_name', 'N/A')}', ship_to.name: '{ship_to_data.get('name', 'N/A')}'")

    # Get customer ID with validation - this should be the numerical RFMS customer ID from the UI
    sold_to_customer_id = sold_to_data.get("id") or sold_to_data.get("customer_source_id")
    if not sold_to_customer_id:
        raise PayloadError("Missing Sold To customer ID for export")
    
    # Ensure it's treated as a string for the API
    sold_to_customer_id = str(sold_to_customer_id)

    # Extract supervisor information with fallbacks
    supervisor_name = job_details_data.get("supervisor_name", "")
    if not supervisor_name:
        supervisor_name = f"{sold_to_data.get('first_name', 'Unknown')} {sold_to_data.get('last_name', 'Supervisor')}"

    supervisor_phone = (
        job_details_data.get("supervisor_phone") or 
        job_details_data.get("supervisor_mobile") or 
        ship_to_data.get("pdf_phone3") or 
        ship_to_data.get("phone1", "") or 
        "0447012125"  # Default fallback
    )

    
    # Generate PO number and job number
    po_number = job_details_data.get("po_number", f"PDF-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    job_number = f"{supervisor_name} & {supervisor_phone}"  # SUPERVISOR NAME & SUPERVISOR PHONE/MOBILE FROM PDF EXTRACTED DATA VERIFIED IN UI SOLDTO DATA SUBMITTED

    # Build custom notes from alternate contacts
    custom_note_lines = []
    alt_contact = export_data.get("alternate_contact", {})
    alt_contacts_list = export_data.get("alternate_contacts", [])
    
    if alt_contact and (alt_contact.get("name") or alt_contact.get("phone") or alt_contact.get("email")):
        best_contact_str = f"Best Contact: {alt_contact.get('name', '')} {alt_contact.get('phone', '')}"
        if alt_contact.get("phone2"):
            best_contact_str += f", {alt_contact.get('phone2')}"
        if alt_contact.get("email"):
            best_contact_str += f" ({alt_contact.get('email')})"
        custom_note_lines.append(best_contact_str)
    
    for contact in alt_contacts_list:
        if contact.get("name") or contact.get("phone") or contact.get("email"):
            line = f"{contact.get('type', 'Contact')}: {contact.get('name', '')} {contact.get('phone', '')}"
            if contact.get("phone2"):
                line += f", {contact.get('phone2')}"
            if contact.get("email"):
                line += f" ({contact.get('email')})"
            custom_note_lines.append(line)
    
    custom_note = "\n".join(custom_note_lines).strip()
    
    # Build comprehensive contact list for work order notes
    all_contacts_text = ", ".join([f"{c.get('type', '')}: {c.get('name', '')} {c.get('phone', '')}" for c in alt_contacts_list if c.get('name')])

    # Determine soldTo name fields based on business_name availability
    business_name = sold_to_data.get("business_name", "").strip()
    if business_name:
        # Use business name as lastName, empty firstName for business customers
        sold_to_first_name = ""
        sold_to_last_name = business_name
    else:
        # Fall back to individual first/last names for personal customers
        sold_to_first_name = _get_first_name(sold_to_data)
        sold_to_last_name = _get_last_name(sold_to_data)

    # Build the RFMS payload using the proven AZ002874 method
    order_payload = {
        "category": "Order",  # FIXED HARDCODED
        "poNumber": po_number,  # PURCHASE ORDER NUMBER FROM PDF EXTRACTED DATA VERIFIED IN UI DATA SUBMITTED
        "jobNumber": f"{supervisor_name} & {supervisor_phone}",  # SUPERVISOR NAME & SUPERVISOR PHONE/MOBILE FROM PDF EXTRACTED DATA VERIFIED IN UI SOLDTO DATA SUBMITTED
        "storeNumber": "49",  # FIXED HARDCODED
        "salesperson1": "ZORAN VEKIC",  # PREFERRED SALESPERSON DATA SELECTED & VERIFIED IN UI SOLDTO DATA SUBMITTED FALLBACK DEFAULT OPTION
        "salesperson2": "",  # FIXED HARDCODED
        "soldTo": {
            "customerType": "BUILDERS",  # FIXED HARDCODED
            "customerId": sold_to_customer_id,  # CUSTOMERID DATA VERIFIED IN UI SOLDTO DATA SUBMITTED
            "firstName": sold_to_first_name,  # Business name logic: empty for business, individual name for personal
            "lastName": sold_to_last_name,   # Business name logic: business name for business, last name for personal
            "address1": sold_to_data.get("address1", ""),  # DATA VERIFIED IN UI SOLDTO DATA SUBMITTED
            "address2": sold_to_data.get("address2", ""),  # DATA VERIFIED IN UI SOLDTO DATA SUBMITTED
            "city": sold_to_data.get("city", ""),  # DATA VERIFIED IN UI SOLDTO DATA SUBMITTED
            "state": sold_to_data.get("state") or "QLD",  # Default to QLD if not provided
            "postalCode": sold_to_data.get("zip_code", ""),  # DATA VERIFIED IN UI SOLDTO DATA SUBMITTED
            "phone1": ship_to_data.get("pdf_phone3") or sold_to_data.get("phone") or ship_to_data.get("pdf_phone1", ""),  # Use Phone3 first (Authorised Contact), then soldTo phone, then PDF phone
            "phone2": ship_to_data.get("pdf_phone4") or ship_to_data.get("pdf_phone2", ""),  # Use Phone4 first (Site Contact), then PDF phone2
            "email": sold_to_data.get("email") or ship_to_data.get("email") or "accounts@atozflooringsolutions.com.au"  # Use soldTo email first
        },
        "shipTo": {
            "firstName": _get_first_name({"name": extracted_customer_name}, default_first="Site") if extracted_customer_name else _get_first_name(ship_to_data, default_first="Site"),  # Use extracted customer name from "Insured Owner" field
            "lastName": _get_last_name({"name": extracted_customer_name}, default_last="Customer") if extracted_customer_name else _get_last_name(ship_to_data, default_last="Customer"),   # Use extracted customer name from "Insured Owner" field
            "address1": ship_to_data.get("address1") or ship_to_data.get("ship_to_address1", ""),  # Enhanced: Use ship_to_address1 as fallback from PDF
            "address2": ship_to_data.get("address2") or ship_to_data.get("ship_to_address2", ""),  # Enhanced: Use ship_to_address2 as fallback from PDF
            "city": ship_to_data.get("city") or ship_to_data.get("ship_to_city", ""),  # Enhanced: Use ship_to_city as fallback from PDF
            "state": ship_to_data.get("state") or ship_to_data.get("ship_to_state") or "QLD",  # Enhanced: Use ship_to_state as fallback, default to QLD
            "postalCode": ship_to_data.get("zip_code") or ship_to_data.get("ship_to_zip", "")  # Enhanced: Use ship_to_zip as fallback from PDF
        },
        "privateNotes": f"PO VALUE: ${job_details_data.get('dollar_value', 0)}\nSITE CONTACT: {extracted_customer_name or ship_to_data.get('first_name', '') + ' ' + ship_to_data.get('last_name', '')}\nALTERNATE CONTACT: {alt_contact.get('name', '')}\nOTHER CONTACTS: {', '.join([c.get('name', '') for c in alt_contacts_list])}\nPHONE1: {ship_to_data.get('pdf_phone3', '')}\nPHONE2: {ship_to_data.get('pdf_phone4', '')}",  # FROM PDF EXTRACTED DATA VERIFIED IN UI SHIPTO DATA SUBMITTED
        "publicNotes": f"JOB DESCRIPTION: {job_details_data.get('description_of_works', '')}\nWORKS REQUIRED: {job_details_data.get('works_required', '')}\nSCOPE OF WORKS: {job_details_data.get('scope_of_works', '')}",  # FROM PDF EXTRACTED DATA VERIFIED IN UI SHIPTO DATA SUBMITTED
        "workOrderNotes": f"SITE CONTACT: {extracted_customer_name or ship_to_data.get('first_name', '') + ' ' + ship_to_data.get('last_name', '')}\nALTERNATE CONTACT: {alt_contact.get('name', '')}\nPHONE1: {ship_to_data.get('pdf_phone3', '')}\nPHONE2: {ship_to_data.get('pdf_phone4', '')}\nALL CONTACTS: {all_contacts_text}",  # FROM PDF EXTRACTED DATA VERIFIED IN UI SHIPTO DATA SUBMITTED
        "measureDate": None,  # Set to null as required by RFMS
        "estimatedDeliveryDate": "2025-06-11",  # Use a fixed date to avoid field issues
        "priceLevel": "3",  # FIXED HARDCODED
        "userOrderTypeId": "18",  # FIXED HARDCODED
        "serviceTypeId": "8",  # FIXED HARDCODED
        "contractTypeId": "1",  # FIXED HARDCODED
        "adSourceId": "1",  # FIXED HARDCODED
        "lines": [],  # Empty lines array as shown in working orders
        "products": [
            {
                "productId": "213322",  # FIXED HARDCODED
                "colorId": "2133",  # FIXED HARDCODED
                "quantity": job_details_data.get("dollar_value", 1),  # FROM PDF EXTRACTED DATA VERIFIED IN UI SOLDTO DATA SUBMITTED
                "priceLevel": "10",  # FIXED HARDCODED - use "10" not "Price10"
                "lineGroupId": "4"  # FIXED HARDCODED - required field from working orders
            }
        ]
    }
    
    if logger:
        logger.info(f"Constructed RFMS Order Payload: {json.dumps(order_payload, indent=2)}")

    return order_payload

def export_data_to_rfms(api_client, export_data, logger):
    """
    Main export function that uses the AZ002874 method to create orders in RFMS.
    
    Args:
        api_client: Initialized RfmsApi instance
        export_data (dict): The export data containing all necessary information
        logger: Logger instance for debugging
        
    Returns:
        dict: Result of the export operation
    """
    try:
        # Build the main order payload
        order_payload = build_rfms_order_payload(export_data, logger)
        
        # Create the main job
        job_result = api_client.create_job(order_payload)
        job_id = job_result.get("result") or job_result.get("id")
        
        if not job_id:
            raise Exception(f"Failed to create main job in RFMS. Response: {job_result}")
        
        logger.info(f"RFMS Export Success: Order {job_id} created")

        final_result = {
            "success": True,
            "message": "Successfully exported main job to RFMS",
            "job": job_result,
            "order_id": job_id,
            "sold_to_customer_id": order_payload["soldTo"]["customerId"],
            "format_used": "az002874_flat_structure"
        }

        # Handle billing group if applicable
        if export_data.get("billing_group") and export_data.get("second_job_details"):
            second_job_details = export_data["second_job_details"]
            
            # Create second order payload
            second_order_payload = order_payload.copy()
            second_order_payload["poNumber"] = second_job_details.get("po_number", f"PDF2-{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            # Update notes and job number for second job
            second_order_payload["publicNotes"] = second_job_details.get("description_of_works", "").strip()
            second_supervisor_name = second_job_details.get("supervisor_name", order_payload["jobNumber"].split()[0])
            second_supervisor_phone = second_job_details.get("supervisor_phone", "") or second_job_details.get("supervisor_mobile", "")
            second_job_number = f"{second_supervisor_name} {second_supervisor_phone}".strip() or second_job_details.get("po_number", "")
            second_order_payload["jobNumber"] = second_job_number
            
            logger.info(f"Creating second job in RFMS (billing group): {second_order_payload['poNumber']}")
            second_job_result = api_client.create_job(second_order_payload)
            second_job_id = second_job_result.get("result") or second_job_result.get("id")
            
            if not second_job_id:
                raise Exception(f"Failed to create second job in RFMS. Response: {second_job_result}")
            
            logger.info(f"Second job created in RFMS with ID: {second_job_id}")
            
            # Add to billing group
            billing_group_result = api_client.add_to_billing_group([job_id, second_job_id])
            final_result["second_job"] = second_job_result
            final_result["second_order_id"] = second_job_id
            final_result["billing_group"] = billing_group_result
            final_result["message"] = "Successfully exported main job, second job, and created billing group."
        
        return final_result 

    except Exception as e:
        error_msg = f"Error in export_data_to_rfms: {str(e)}"
        if logger:
            logger.error(error_msg)
        raise PayloadError(error_msg) 