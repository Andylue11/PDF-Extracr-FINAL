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
    
    # Debug logging to see what phone data we're receiving and prioritization
    manual_phone3 = data.get('phone3', '')
    manual_phone4 = data.get('phone4', '')
    manual_phone = data.get('phone', '')
    manual_phone2 = data.get('phone2', '')
    print(f"[DEBUG] Customer payload data received: phone='{manual_phone}', phone2='{manual_phone2}', phone3='{manual_phone3}', phone4='{manual_phone4}'")
    print(f"[DEBUG] Customer phone prioritization - phone1 will be: '{manual_phone3 or manual_phone}', phone2 will be: '{manual_phone4 or manual_phone2}'")

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
    
    # If still no names, provide sensible defaults for RFMS
    if not first_name and not last_name:
        # Use supervisor name as fallback if available
        supervisor_name = data.get("supervisor_name", "")
        if supervisor_name:
            name_parts = supervisor_name.split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = " ".join(name_parts[1:])
            else:
                first_name = supervisor_name
                last_name = "Customer"
        else:
            # Last resort - use descriptive defaults
            first_name = "Site"
            last_name = "Customer"
    elif not first_name:
        first_name = "Site"
    elif not last_name:
        last_name = "Customer"

    print(f"[DEBUG] Final customer names - first_name: '{first_name}', last_name: '{last_name}'")

    # Build customer-specific payload matching RFMS API documentation exactly
    payload = {
        "customerType": "INSURANCE",  # Required by RFMS for customer creation
        "entryType": "Customer",  # Required by RFMS for customer creation (from API docs)
        "customerAddress": {
            "lastName": last_name,
            "firstName": first_name,
            # Prioritize manual UI data over any PDF extracted data
            "address1": data.get("address1", "") or data.get("ship_to_address1", ""),  # Manual first, PDF fallback
            "address2": data.get("address2", "") or data.get("ship_to_address2", ""),  # Manual first, PDF fallback
            "city": data.get("city", "") or data.get("ship_to_city", ""),  # Manual first, PDF fallback
            "state": data.get("state", "") or data.get("ship_to_state", "") or "QLD",  # Manual first, PDF fallback, default QLD
            "postalCode": data.get("zip_code", "") or data.get("ship_to_zip", ""),  # Manual first, PDF fallback
            "county": ""  # Optional field from API docs
        },
        "shipToAddress": {
            "lastName": last_name,
            "firstName": first_name,
            # Prioritize manual UI data over any PDF extracted data
            "address1": data.get("address1", "") or data.get("ship_to_address1", ""),  # Manual first, PDF fallback
            "address2": data.get("address2", "") or data.get("ship_to_address2", ""),  # Manual first, PDF fallback
            "city": data.get("city", "") or data.get("ship_to_city", ""),  # Manual first, PDF fallback
            "state": data.get("state", "") or data.get("ship_to_state", "") or "QLD",  # Manual first, PDF fallback, default QLD
            "postalCode": data.get("zip_code", "") or data.get("ship_to_zip", ""),  # Manual first, PDF fallback
            "county": ""  # Optional field from API docs
        },
        "phone1": data.get("phone3", "") or data.get("phone", "") or data.get("pdf_phone3", "") or data.get("pdf_phone1", ""),  # Prioritize manual phone3, then phone, then PDF data
        "phone2": data.get("phone4", "") or data.get("phone2", "") or data.get("pdf_phone4", "") or data.get("pdf_phone2", ""),  # Prioritize manual phone4, then phone2, then PDF data
        "customerPhone3": data.get("phone3", ""),  # Support RFMS customerPhone3 field directly
        "customerPhone4": data.get("phone4", ""),  # Support RFMS customerPhone4 field directly 
        "email": data.get("email", "") or data.get("pdf_email", ""),  # Prioritize manual email, fallback to PDF email
        "taxStatus": "Tax",  # From API docs
        "taxMethod": "SalesTax",  # From API docs
        "preferredSalesperson1": "ZORAN VEKIC",
        "preferredSalesperson2": "",
        "storeNumber": "49"
    }
    
    # Debug logging to show final values being sent to RFMS
    final_phone1 = payload["phone1"]
    final_phone2 = payload["phone2"]
    print(f"[DEBUG] Customer creation final values - phone1: '{final_phone1}', phone2: '{final_phone2}', customerPhone3: '{payload['customerPhone3']}', customerPhone4: '{payload['customerPhone4']}'")
    
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

    # Note: soldTo name fields not needed when customer ID is provided - RFMS has all customer details

    # Debug logging to track data source prioritization
    if logger:
        manual_phone3 = sold_to_data.get('phone3', '')
        manual_phone4 = sold_to_data.get('phone4', '')
        pdf_phone3 = ship_to_data.get('pdf_phone3', '')
        pdf_phone4 = ship_to_data.get('pdf_phone4', '')
        logger.info(f"[ORDER_PAYLOAD] Phone prioritization - Manual: phone3='{manual_phone3}', phone4='{manual_phone4}' | PDF: pdf_phone3='{pdf_phone3}', pdf_phone4='{pdf_phone4}'")
        logger.info(f"[ORDER_PAYLOAD] Final phones - phone1='{sold_to_data.get('phone3') or sold_to_data.get('phone') or ship_to_data.get('pdf_phone3') or ship_to_data.get('pdf_phone1', '')}', phone2='{sold_to_data.get('phone4') or sold_to_data.get('phone2') or ship_to_data.get('pdf_phone4') or ship_to_data.get('pdf_phone2', '')}'")

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
            # When customer ID is provided, RFMS has all customer details - only need phone numbers for contact
            "phone1": sold_to_data.get("phone3") or sold_to_data.get("phone") or ship_to_data.get("pdf_phone3") or ship_to_data.get("pdf_phone1", ""),  # Prioritize manual phone3, then phone, then PDF data
            "phone2": sold_to_data.get("phone4") or sold_to_data.get("phone2") or ship_to_data.get("pdf_phone4") or ship_to_data.get("pdf_phone2", "")  # Prioritize manual phone4, then phone2, then PDF data
        },
        "shipTo": {
            # Prioritize manual UI data for names, fallback to PDF extraction
            "firstName": _get_first_name(ship_to_data, default_first="Site") if ship_to_data.get("first_name") or ship_to_data.get("name") else (_get_first_name({"name": extracted_customer_name}, default_first="Site") if extracted_customer_name else "Site"),
            "lastName": _get_last_name(ship_to_data, default_last="Customer") if ship_to_data.get("last_name") or ship_to_data.get("name") else (_get_last_name({"name": extracted_customer_name}, default_last="Customer") if extracted_customer_name else "Customer"),
            # Prioritize manual UI address data over PDF extracted data
            "address1": ship_to_data.get("address1") or ship_to_data.get("ship_to_address1", ""),  # Manual first, PDF fallback
            "address2": ship_to_data.get("address2") or ship_to_data.get("ship_to_address2", ""),  # Manual first, PDF fallback
            "city": ship_to_data.get("city") or ship_to_data.get("ship_to_city", ""),  # Manual first, PDF fallback
            "state": ship_to_data.get("state") or ship_to_data.get("ship_to_state") or "QLD",  # Manual first, PDF fallback, default QLD
            "postalCode": ship_to_data.get("zip_code") or ship_to_data.get("ship_to_zip", "")  # Manual first, PDF fallback
        },
        "privateNotes": f"PO VALUE: ${job_details_data.get('dollar_value', 0)}\nSITE CONTACT: {extracted_customer_name or ship_to_data.get('first_name', '') + ' ' + ship_to_data.get('last_name', '')}\nALTERNATE CONTACT: {alt_contact.get('name', '')}\nOTHER CONTACTS: {', '.join([c.get('name', '') for c in alt_contacts_list])}\nPHONE1: {sold_to_data.get('phone3') or sold_to_data.get('phone') or ship_to_data.get('pdf_phone3', '')}\nPHONE2: {sold_to_data.get('phone4') or sold_to_data.get('phone2') or ship_to_data.get('pdf_phone4', '')}",  # Prioritize manual UI data over PDF extracted data
        "publicNotes": f"JOB DESCRIPTION: {job_details_data.get('description_of_works', '')}\nWORKS REQUIRED: {job_details_data.get('works_required', '')}\nSCOPE OF WORKS: {job_details_data.get('scope_of_works', '')}",  # FROM PDF EXTRACTED DATA VERIFIED IN UI SHIPTO DATA SUBMITTED
        "workOrderNotes": f"SITE CONTACT: {extracted_customer_name or ship_to_data.get('first_name', '') + ' ' + ship_to_data.get('last_name', '')}\nALTERNATE CONTACT: {alt_contact.get('name', '')}\nPHONE1: {sold_to_data.get('phone3') or sold_to_data.get('phone') or ship_to_data.get('pdf_phone3', '')}\nPHONE2: {sold_to_data.get('phone4') or sold_to_data.get('phone2') or ship_to_data.get('pdf_phone4', '')}\nALL CONTACTS: {all_contacts_text}",  # Prioritize manual UI data over PDF extracted data
        "measureDate": None,  # Set to null as required by RFMS
        "estimatedDeliveryDate": "2025-06-11",  # Use a fixed date to avoid field issues
        "priceLevel": "3",  # FIXED HARDCODED
        "userOrderTypeId": "18",  # FIXED HARDCODED
        "serviceTypeId": "8",  # FIXED HARDCODED
        "contractTypeId": "1",  # FIXED HARDCODED
        "adSourceId": "1",  # FIXED HARDCODED
        "lines": [
            {
                "productId": "1265",  # PURCHASE ORDER VALUE EX GST product ID
                "productCode": "38",  # Product code from RFMS API response
                "styleName": "PURCHASE ORDER VALUE EX GST",  # Product name
                "styleNumber": "PO$VALUE",  # Style number from RFMS
                "colorId": "3072",  # Color ID for PO$$VALUE
                "colorName": "PO$$VALUE",  # Color name from RFMS
                "colorNumber": "$$XGST",  # Color number from RFMS
                "quantity": job_details_data.get("dollar_value", 1),  # Use dollar value as quantity
                "priceLevel": "Price10",  # Price level as requested
                "lineGroupId": "4"  # Required field from working orders
            }
        ],
        "products": [
            {
                "productId": "1265",  # FIXED HARDCODED
                "colorId": "3072",  # FIXED HARDCODED
                "quantity": job_details_data.get("dollar_value", 1),  # FROM PDF EXTRACTED DATA VERIFIED IN UI SOLDTO DATA SUBMITTED
                "priceLevel": "10",  # FIXED HARDCODED - use "10" not "Price10"
                "lineGroupId": "4"  # FIXED HARDCODED - required field from working orders
            }
        ]
    }
    
    # Add billing group data if applicable
    billing_group_data = export_data.get("billing_group", {})
    if billing_group_data and billing_group_data.get("is_billing_group"):
        # Build contact list from alternate contacts (up to 4)
        contact_list = []
        
        # Add primary contact (best contact)
        if alt_contact and alt_contact.get("name"):
            contact_entry = {
                "name": alt_contact.get("name", ""),
                "phone": alt_contact.get("phone", ""),
                "email": alt_contact.get("email", "")
            }
            if alt_contact.get("phone2"):
                contact_entry["other"] = alt_contact.get("phone2")
            contact_list.append(contact_entry)
        
        # Add alternate contacts (up to 3 more for total of 4)
        for contact in alt_contacts_list[:3]:  # Limit to 3 more
            if contact.get("name"):
                contact_entry = {
                    "name": contact.get("name", ""),
                    "phone": contact.get("phone", ""),
                    "email": contact.get("email", "")
                }
                if contact.get("phone2"):
                    contact_entry["other"] = contact.get("phone2")
                contact_list.append(contact_entry)
        
        # Create ship-to address description
        ship_to_address = f"{ship_to_data.get('address1', '')} {ship_to_data.get('address2', '')}".strip()
        if ship_to_data.get('city'):
            ship_to_address += f", {ship_to_data.get('city')}"
        if ship_to_data.get('state'):
            ship_to_address += f", {ship_to_data.get('state')}"
        if ship_to_data.get('zip_code'):
            ship_to_address += f" {ship_to_data.get('zip_code')}"
        
        order_payload["billingGroup"] = {
            "description": ship_to_address or f"Project - {po_number}",
            "contactList": contact_list[:4]  # Ensure max 4 contacts
        }
        
        if logger:
            logger.info(f"[BILLING_GROUP] Added billing group data with {len(contact_list)} contacts")
    
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
        billing_group_data = export_data.get("billing_group", {})
        if billing_group_data and billing_group_data.get("is_billing_group"):
            # Create second order payload with PO suffix
            second_order_payload = order_payload.copy()
            
            # Build second PO number with suffix - remove existing suffix first
            original_po = order_payload["poNumber"]
            po_suffix = billing_group_data.get("po_suffix", "")
            
            # Remove existing suffix if present (everything after the last dash)
            if '-' in original_po:
                base_po = '-'.join(original_po.split('-')[:-1])  # Remove last part after dash
            else:
                base_po = original_po
            
            second_po_number = f"{base_po}-{po_suffix}" if po_suffix else f"{base_po}-2"
            second_order_payload["poNumber"] = second_po_number
            
            # Update private notes to include dollar value from manual entry
            second_dollar_value = billing_group_data.get("dollar_value", 0)
            second_order_payload["privateNotes"] = f"PO VALUE: ${second_dollar_value}\n{order_payload['privateNotes']}"
            
            # Update the product quantity to use the second order's dollar value
            second_order_payload["products"][0]["quantity"] = second_dollar_value
            
            # Remove the billingGroup data from second order and add parentOrder reference
            if "billingGroup" in second_order_payload:
                del second_order_payload["billingGroup"]
            
            # Add billing group reference to parent order
            second_order_payload["billingGroup"] = {
                "parentOrder": job_id
            }
            
            logger.info(f"Creating second job in RFMS (billing group): {second_order_payload['poNumber']}")
            second_job_result = api_client.create_job(second_order_payload)
            second_job_id = second_job_result.get("result") or second_job_result.get("id")
            
            if not second_job_id:
                raise Exception(f"Failed to create second job in RFMS. Response: {second_job_result}")
            
            logger.info(f"Second job created in RFMS with ID: {second_job_id}")
            
            final_result["second_job"] = second_job_result
            final_result["second_order_id"] = second_job_id
            final_result["billing_group"] = {"parentOrder": job_id, "childOrder": second_job_id}
            final_result["message"] = "Successfully exported main job and second job with billing group reference."
        
        return final_result 

    except Exception as e:
        error_msg = f"Error in export_data_to_rfms: {str(e)}"
        if logger:
            logger.error(error_msg)
        raise PayloadError(error_msg) 