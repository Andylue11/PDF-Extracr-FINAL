/**
 * RFMS PDF XTRACR - Main JavaScript
 * Common functionality used across the application
 */

// Configuration
const API_CONFIG = {
    TIMEOUT: 30000, // 30 seconds
    RETRY_ATTEMPTS: 2,
    RETRY_DELAY: 1000 // 1 second
};

// Check API status on page load
document.addEventListener('DOMContentLoaded', function() {
    checkApiStatus();
    // loadSalespersonValues(); // Commented out - using hardcoded values in HTML
    
    // Set up other global event listeners
    setupFormValidation();
    setupPdfUpload();
    setupBuilderSearch();
    setupAddCustomerAndCreateJob();
    setupClearSoldToButton();
    enforceBuilderSelectionBeforeUpload();
});

/**
 * Set up Clear SOLD To button functionality
 */
function setupClearSoldToButton() {
    const clearSoldToBtn = document.getElementById('clear-sold-to-btn');
    if (clearSoldToBtn) {
        clearSoldToBtn.addEventListener('click', function() {
            // Clear search field
            const searchField = document.getElementById('sold-to-search');
            if (searchField) searchField.value = '';
            
            // Clear search results
            const resultsDiv = document.getElementById('sold-to-results');
            if (resultsDiv) resultsDiv.innerHTML = '';
            
            // Clear visible fields
            const visibleFields = [
                'sold-to-rfms-id',
                'sold-to-name',
                'sold-to-address1',
                'sold-to-address2',
                'sold-to-city',
                'sold-to-zip'
            ];
            
            visibleFields.forEach(id => {
                const field = document.getElementById(id);
                if (field) field.value = '';
            });
            
            // Clear hidden fields too
            const hiddenFields = [
                'sold-to-business-name',
                'sold-to-state',
                'sold-to-phone1',
                'sold-to-phone2',
                'sold-to-email'
            ];
            
            hiddenFields.forEach(id => {
                const field = document.getElementById(id);
                if (field) field.value = '';
            });
            
            // Reset salesperson dropdown to default (ZORAN VEKIC)
            const salespersonDropdown = document.getElementById('sold-to-salesperson');
            if (salespersonDropdown) {
                // Find the ZORAN VEKIC option and select it
                for (let i = 0; i < salespersonDropdown.options.length; i++) {
                    if (salespersonDropdown.options[i].value === 'ZORAN VEKIC') {
                        salespersonDropdown.selectedIndex = i;
                        break;
                    }
                }
            }
            
            console.log('Sold To fields cleared');
        });
    }
}

/**
 * Load salesperson values for the dropdown
 */
async function loadSalespersonValues() {
    const salespersonSelect = document.getElementById('sold-to-salesperson');
    
    if (!salespersonSelect) {
        console.error('Salesperson dropdown not found.');
        return;
    }
    
    // Skip if we already have options (hardcoded in HTML)
    if (salespersonSelect.options.length > 1) {
        console.log('Salesperson values already loaded from HTML');
        return;
    }
    
    try {
        const response = await fetchWithRetry('/api/salesperson_values');
        const salespersonValues = await response.json();
        
        if (Array.isArray(salespersonValues)) {
            // Clear existing options except the first placeholder
            salespersonSelect.innerHTML = '<option value="">Select Salesperson</option>';
            
            // Add new options
            salespersonValues.forEach(value => {
                const option = document.createElement('option');
                option.value = value;
                option.textContent = value;
                salespersonSelect.appendChild(option);
            });
            
            console.log('Loaded salesperson values:', salespersonValues);
        }
    } catch (error) {
        console.error('Error loading salesperson values:', error);
        // Add default value as fallback
        const option = document.createElement('option');
        option.value = 'ZORAN VEKIC';
        option.textContent = 'ZORAN VEKIC';
        salespersonSelect.appendChild(option);
    }
}

/**
 * Fetch with timeout and retry capability
 * @param {string} url - The URL to fetch from
 * @param {Object} options - Fetch options
 * @param {number} retryCount - Current retry count
 * @returns {Promise} - Fetch promise with timeout and retry handling
 */
async function fetchWithRetry(url, options = {}, retryCount = 0) {
    // Add timeout to fetch using AbortController
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);
    
    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal
        });
        
        // Clear timeout since request completed
        clearTimeout(timeoutId);
        
        // Handle HTTP errors
        if (!response.ok) {
            // Get error details from response if possible
            let errorMessage = `HTTP error ${response.status}: ${response.statusText}`;
            try {
                const errorData = await response.json();
                if (errorData && errorData.error) {
                    errorMessage = errorData.error;
                }
            } catch (e) {
                // Unable to parse error response, use default error message
            }
            
            const error = new Error(errorMessage);
            error.status = response.status;
            throw error;
        }
        
        return response;
        
    } catch (error) {
        // Clear timeout if request failed
        clearTimeout(timeoutId);
        
        // Handle request timeout
        if (error.name === 'AbortError') {
            console.error('Request timeout');
            error.message = 'Request timed out. Please try again.';
        }
        
        // Retry logic for specific errors
        if (retryCount < API_CONFIG.RETRY_ATTEMPTS && 
            (error.status >= 500 || error.name === 'AbortError' || error.message.includes('network'))) {
            console.log(`Retrying request (${retryCount + 1}/${API_CONFIG.RETRY_ATTEMPTS})...`);
            
            // Wait before retrying
            await new Promise(resolve => setTimeout(resolve, API_CONFIG.RETRY_DELAY));
            
            return fetchWithRetry(url, options, retryCount + 1);
        }
        
        throw error;
    }
}

/**
 * Centralized error handler for API requests
 * @param {Error} error - The error object
 * @param {string} operation - The operation being performed
 * @returns {string} - User-friendly error message
 */
function handleApiError(error, operation) {
    console.error(`Error during ${operation}:`, error);
    
    // Default error message
    let userMessage = `An error occurred while ${operation}. Please try again.`;
    
    // Customize message based on error type
    if (error.name === 'AbortError') {
        userMessage = `Request timed out while ${operation}. Please check your connection and try again.`;
    } else if (error.status === 401 || error.status === 403) {
        userMessage = `Authentication failed while ${operation}. Please log in again.`;
    } else if (error.status === 404) {
        userMessage = `Resource not found while ${operation}.`;
    } else if (error.status >= 500) {
        userMessage = `Server error while ${operation}. Please try again later.`;
    } else if (error.message) {
        userMessage = error.message;
    }
    
    // Display error to user
    showNotification(userMessage, 'error');
    
    return userMessage;
}

/**
 * Check RFMS API status and update UI indicator
 */
function checkApiStatus() {
    const indicator = document.getElementById('api-status-indicator');
    const text = document.getElementById('api-status-text');
    
    if (!indicator || !text) return;
    
    // Set initial state
    indicator.classList.remove('bg-green-500', 'bg-red-500');
    indicator.classList.add('bg-gray-400');
    text.textContent = 'RFMS API: Checking...';
    text.classList.remove('text-green-600', 'text-red-600');
    text.classList.add('text-gray-600');
    
    fetchWithRetry('/api/check_status')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'online') {
                indicator.classList.remove('bg-gray-400', 'bg-red-500');
                indicator.classList.add('bg-green-500');
                text.textContent = 'RFMS API: Online';
                text.classList.remove('text-gray-600', 'text-red-600');
                text.classList.add('text-green-600');
            } else {
                indicator.classList.remove('bg-gray-400', 'bg-green-500');
                indicator.classList.add('bg-red-500');
                text.textContent = 'RFMS API: Offline';
                text.classList.remove('text-gray-600', 'text-green-600');
                text.classList.add('text-red-600');
            }
        })
        .catch(error => {
            handleApiError(error, 'checking API status');
            indicator.classList.remove('bg-gray-400', 'bg-green-500');
            indicator.classList.add('bg-red-500');
            text.textContent = 'RFMS API: Error';
            text.classList.remove('text-gray-600', 'text-green-600');
            text.classList.add('text-red-600');
        });
}

/**
 * Set up form validation for common forms
 */
function setupFormValidation() {
    // Get all forms with the 'needs-validation' class
    const forms = document.querySelectorAll('form.needs-validation');
    
    // Loop over them and prevent submission
    Array.from(forms).forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            
            form.classList.add('was-validated');
        }, false);
    });
}

/**
 * Format currency value as USD
 * @param {number} value - The value to format
 * @returns {string} - Formatted currency string
 */
function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(value);
}

/**
 * Format phone number in standard US format (or suitable for AU)
 * @param {string} phoneNumberString - The phone number to format
 * @returns {string} - Formatted phone number
 */
function formatPhoneNumber(phoneNumberString) {
    // Keep only digits
    const cleaned = ('' + phoneNumberString).replace(/\D/g, '');
    
    // Attempt Australian mobile format 04xx xxx xxx
    if (cleaned.length === 10 && cleaned.startsWith('04')) {
        return cleaned.replace(/^(\d{4})(\d{3})(\d{3})$/, '$1 $2 $3');
    }
     // Attempt Australian landline format 0x xxxx xxxx
    if (cleaned.length === 10 && cleaned.startsWith('0') && !cleaned.startsWith('04')) {
         return cleaned.replace(/^(\d{1})(\d{4})(\d{4})$/, '$1 $2 $3');
    }
     // Attempt International format +61 x xxx xxx xxx
    if (cleaned.length === 11 && cleaned.startsWith('61')) {
         return '+' + cleaned.replace(/^(\d{2})(\d{1})(\d{4})(\d{4})$/, '$1 $2 $3 $4');
    }
    
    // If no specific format matches, return cleaned or original
    return phoneNumberString; // Or return cleaned if preferred
}

/**
 * Helper function to safely set value to an element by ID
 * @param {string} elementId - The ID of the element
 * @param {string} value - The value to set
 */
function setValue(elementId, value) {
    const element = document.getElementById(elementId);
    if (element) {
        element.value = value || '';
    } else {
        console.warn(`Element with id '${elementId}' not found`);
    }
}

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - The type of notification (success, error, warning, info)
 * @param {number} duration - Duration in milliseconds
 * @returns {HTMLElement} - The notification element
 */
function showNotification(message, type = 'info', duration = 3000) {
    // Remove any existing notification with id 'notification-loading'
    const existingNotification = document.getElementById('notification-loading');
    if (existingNotification) {
        document.body.removeChild(existingNotification);
    }
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `fixed bottom-4 right-4 px-6 py-3 rounded-md shadow-lg text-white ${
        type === 'success' ? 'bg-green-500' :
        type === 'error' ? 'bg-red-500' :
        type === 'warning' ? 'bg-yellow-500' :
        'bg-blue-500'
    } transition-opacity duration-300 ease-in-out opacity-0 z-50`;
    
    // For loading notifications, add an ID to allow removal later
    if (duration === 0) {
        notification.id = 'notification-loading';
    }
    
    notification.textContent = message;
    
    // Add to DOM
    document.body.appendChild(notification);
    
    // Fade in
    setTimeout(() => {
        notification.classList.add('opacity-100');
        notification.classList.remove('opacity-0');
    }, 10);
    
    // Remove after duration (if not a persistent notification)
    if (duration > 0) {
        setTimeout(() => {
            notification.classList.remove('opacity-100');
            notification.classList.add('opacity-0');
            
            setTimeout(() => {
                if (document.body.contains(notification)) {
                    document.body.removeChild(notification);
                }
            }, 300);
        }, duration);
    }
    
    return notification;
}

/**
 * Clear all form fields in the application
 */
function clearFields() {
    // Clear all input fields
    const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="number"], textarea');
    inputs.forEach(input => {
        input.value = '';
    });
    
    // Clear checkboxes
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        checkbox.checked = false;
    });
    
    // Hide secondary PO details if visible
    const secondaryPoDetails = document.getElementById('secondary-po-details');
    if (secondaryPoDetails) {
        secondaryPoDetails.classList.add('hidden');
    }
}

/**
 * Set up PDF upload functionality
 */
function setupPdfUpload() {
    console.log('[DEBUG] Setting up PDF upload...');
    const uploadBtn = document.getElementById('upload-pdf-btn');
    const fileInput = document.getElementById('pdf-file-input');
    const clearDataBtn = document.getElementById('clear-data-btn');

    if (!uploadBtn || !fileInput) {
        console.error('[DEBUG] PDF upload elements not found:', {
            uploadBtn: !!uploadBtn,
            fileInput: !!fileInput
        });
        return;
    }
    console.log('[DEBUG] PDF upload elements found successfully');

    // Upload button click handler
    try {
        uploadBtn.addEventListener('click', (event) => {
            console.log('[DEBUG] Upload button clicked', {
                eventType: event.type,
                target: event.target.id,
                currentTarget: event.currentTarget.id,
                defaultPrevented: event.defaultPrevented,
                bubbles: event.bubbles,
                cancelable: event.cancelable
            });
            event.preventDefault(); // Prevent any default form submission
            event.stopPropagation(); // Stop event bubbling
            console.log('[DEBUG] Triggering file input click');
        fileInput.click();
    });
        console.log('[DEBUG] Upload button click handler attached successfully');
    } catch (error) {
        console.error('[DEBUG] Error attaching upload button click handler:', error);
    }
    
    // File input change handler
    try {
    fileInput.addEventListener('change', async (event) => {
            console.log('[DEBUG] File input change event triggered');
        const file = event.target.files[0];
            if (!file) {
                console.log('[DEBUG] No file selected');
                return;
            }
            console.log('[DEBUG] PDF upload started for file:', file.name);

        // Get the selected builder name from the sold-to fields
        const builderName = document.getElementById('sold-to-name')?.value || '';
            console.log('[DEBUG] Selected builder name:', builderName);

        const formData = new FormData();
        formData.append('pdf_file', file);
        formData.append('builder_name', builderName);
        
        try {
                console.log('[DEBUG] Disabling upload button');
            uploadBtn.disabled = true;
            uploadBtn.textContent = 'Uploading...';

                console.log('[DEBUG] Sending upload request to /upload-pdf');
            const response = await fetch('/upload-pdf', {
                method: 'POST',
                body: formData
            });
            
                console.log('[DEBUG] Upload response received:', response.status);
            if (!response.ok) {
                let errorMsg = `Upload failed: ${response.statusText}`;
                try {
                    const errJson = await response.json();
                    if (errJson && errJson.error) errorMsg = errJson.error;
                    } catch (e) {
                        console.error('[DEBUG] Error parsing error response:', e);
                    }
                showNotification(errorMsg, 'error', 6000);
                console.error('[DEBUG] PDF upload error:', errorMsg);
                return;
            }

                console.log('[DEBUG] Parsing response JSON');
            const extractedData = await response.json();
            if (extractedData.error) {
                showNotification('Extraction error: ' + extractedData.error, 'error', 6000);
                console.error('[DEBUG] Extraction error:', extractedData.error);
                return;
            }
                
                console.log('[DEBUG] Successfully extracted data:', extractedData);
            
            // Extract data into form fields
            if (extractedData) {
                // Check for builder mismatch warning
                if (extractedData.builder_mismatch_warning) {
                    const continueWithMismatch = confirm(
                        extractedData.builder_mismatch_warning + 
                        "\n\nDo you want to continue with the extraction anyway?"
                    );
                    if (!continueWithMismatch) {
                        showNotification('PDF upload cancelled. Please select the correct builder.', 'warning');
                        return;
                    }
                }
                
                // Populate ship-to fields
                setValue('ship-to-name', extractedData.customer_name || '');
                    
                    // Split customer name into first and last names for customer creation
                    if (extractedData.customer_name) {
                        const nameParts = extractedData.customer_name.trim().split(/\s+/);
                        if (nameParts.length >= 2) {
                            setValue('ship-to-first-name', nameParts[0]);
                            setValue('ship-to-last-name', nameParts.slice(1).join(' '));
                        } else if (nameParts.length === 1) {
                            setValue('ship-to-first-name', '');
                            setValue('ship-to-last-name', nameParts[0]);
                        }
                    }
                    
                    setValue('ship-to-address1', extractedData.address1 || extractedData.address || '');  // Use parsed address1 first
                setValue('ship-to-address2', extractedData.address2 || '');
                setValue('ship-to-city', extractedData.city || '');
                setValue('ship-to-zip', extractedData.zip_code || '');
                    setValue('ship-to-state', extractedData.state || '');
                setValue('ship-to-email', extractedData.email || '');
                
                // Populate phone fields
                setValue('ship-to-phone1', extractedData.phone || '');
                setValue('ship-to-phone2', extractedData.mobile || extractedData.work_phone || '');
                    
                    // Also populate hidden PDF phone fields for customer creation
                    setValue('pdf-phone1', extractedData.phone || '');
                    setValue('pdf-phone2', extractedData.mobile || extractedData.work_phone || '');
                
                // Populate work order fields
                setValue('po-number', extractedData.po_number || '');
                setValue('dollar-value', extractedData.dollar_value || '');
                setValue('description-of-works', extractedData.scope_of_work || extractedData.description_of_works || '');
                
                    // Populate supervisor fields
                    setValue('supervisor-name', extractedData.supervisor_name || '');
                    setValue('supervisor-phone', extractedData.supervisor_mobile || extractedData.supervisor_phone || '');
                
                // Populate dates if available
                if (extractedData.commencement_date) {
                    setValue('commencement-date', extractedData.commencement_date);
                }
                if (extractedData.installation_date || extractedData.completion_date) {
                    setValue('completion-date', extractedData.installation_date || extractedData.completion_date);
                }
                
                // Handle best contacts if available - populate the alternate contact name field
                if (extractedData.alternate_contacts && extractedData.alternate_contacts.length > 0) {
                    // Find the best contact using priority
                    let bestContact = null;
                    const priorities = ['Decision Maker', 'Best Contact', 'Site Contact', 'Authorised Contact', 'Occupant Contact'];
                    for (const type of priorities) {
                        bestContact = extractedData.alternate_contacts.find(c => c.type && c.type.toLowerCase().includes(type.toLowerCase()));
                        if (bestContact) break;
                    }
                    if (!bestContact && extractedData.alternate_contacts.length > 0) {
                        bestContact = extractedData.alternate_contacts[0];
                    }
                    
                    if (bestContact) {
                        setValue('alternate-contact-name', bestContact.name || '');
                    }
                }
                
                // Handle Phone 3 and Phone 4 from extra_phones (Authorised Contact and Site Contact)
                if (extractedData.extra_phones && extractedData.extra_phones.length > 0) {
                    setValue('alternate-contact-phone', extractedData.extra_phones[0] || '');  // Phone 3
                    if (extractedData.extra_phones.length > 1) {
                        setValue('alternate-contact-phone2', extractedData.extra_phones[1] || '');  // Phone 4
                    }
                }
            }
            
            showNotification('PDF uploaded and data extracted successfully!', 'success');
            
        } catch (error) {
            console.error('[DEBUG] Upload error:', error);
            showNotification(`Upload failed: ${error.message}`, 'error', 6000);
        } finally {
            uploadBtn.disabled = false;
            uploadBtn.textContent = 'Upload PDF';
            fileInput.value = '';
            console.log('[DEBUG] PDF upload finished');
        }
    });
        console.log('[DEBUG] File input change handler attached successfully');
    } catch (error) {
        console.error('[DEBUG] Error attaching file input change handler:', error);
    }
            
    // Clear data button handler
    if (clearDataBtn) {
        clearDataBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to clear all data? This will not affect the Sold To (Builder) information.')) {
                // Clear work order fields
                const workOrderFields = [
                    'po-number',
                    'dollar-value',
                    'description-of-works',
                    'commencement-date',
                    'completion-date',
                    'supervisor-name',
                    'supervisor-phone'
                ];
                
                workOrderFields.forEach(id => {
                    const field = document.getElementById(id);
                    if (field) field.value = '';
                });
                
                // Clear ship-to fields
                const shipToFields = [
                    'ship-to-first-name',
                    'ship-to-last-name',
                    'ship-to-name',
                    'ship-to-address1',
                    'ship-to-address2',
                    'ship-to-city',
                    'ship-to-state',
                    'ship-to-zip',
                    'ship-to-county',
                    'ship-to-phone1',
                    'ship-to-phone2',
                    'ship-to-email',
                    'pdf-phone1',
                    'pdf-phone2'
                ];
                
                shipToFields.forEach(id => {
                    const field = document.getElementById(id);
                    if (field) field.value = '';
                });
                
                // Clear best contacts
                clearBestContacts();
                
                // Clear alternate contacts
                const altContactsDiv = document.getElementById('alternate-contacts');
                if (altContactsDiv) altContactsDiv.innerHTML = '';
                
                console.log('Data cleared (Sold To information preserved)');
                showNotification('Data cleared successfully. Sold To information preserved.', 'success');
        }
    });
    }
}

/**
 * Populate the Ship To and Work Details fields with extracted data.
 * This function is moved from the HTML sketch.
 * @param {object} data - The extracted data object from the backend.
 */
function populateShipTo(data) {
    // Ship To fields
    document.getElementById('ship-to-name').value = data.customer_name || '';
    document.getElementById('ship-to-address1').value = data.address1 || '';
    document.getElementById('ship-to-address2').value = data.address2 || '';
    document.getElementById('ship-to-city').value = data.city || '';
    document.getElementById('ship-to-zip').value = data.zip_code || '';
    if (document.getElementById('ship-to-country')) document.getElementById('ship-to-country').value = data.country || '';

    // Work Order Details
    document.getElementById('po-number').value = data.po_number || '';
    document.getElementById('dollar-value').value = data.dollar_value || '';
    document.getElementById('supervisor-name').value = data.supervisor_name || '';
    document.getElementById('supervisor-phone').value = data.supervisor_phone || data.supervisor_mobile || '';
    document.getElementById('description-of-works').value = data.description_of_works || '';

    // Email
    document.getElementById('ship-to-email').value = data.email || '';

    // Phone numbers: prioritize phone, mobile, then extras
    let phoneNumbers = [];
    if (data.phone) phoneNumbers.push(data.phone);
    if (data.mobile && data.mobile !== data.phone) phoneNumbers.push(data.mobile);
    if (data.home_phone) phoneNumbers.push(data.home_phone);
    if (data.work_phone) phoneNumbers.push(data.work_phone);
    if (Array.isArray(data.extra_phones)) {
        data.extra_phones.forEach(p => {
            if (p && !phoneNumbers.includes(p)) phoneNumbers.push(p);
        });
    }
    phoneNumbers = [...new Set(phoneNumbers.filter(Boolean))];
    
    // Store original PDF phones in hidden fields for customer creation
    document.getElementById('pdf-phone1').value = phoneNumbers[0] || '';
    document.getElementById('pdf-phone2').value = phoneNumbers[1] || '';
    
    // Phone 1 and Phone 2 fields - populate from regular phone data
    document.getElementById('ship-to-phone1').value = phoneNumbers[0] || '';
    document.getElementById('ship-to-phone2').value = phoneNumbers[1] || '';

    // Best Contact/Alternate Contact section - show ALL contacts with their details
    let allContactsText = '';
    let phone3 = '';
    let phone4 = '';
    
    if (Array.isArray(data.alternate_contacts)) {
        // Build comprehensive contact text showing all contacts
        const contactTexts = [];
        
        // Collect all unique phone numbers first
        const allAvailablePhones = [];
        const extraPhones = data.extra_phones || [];
        
        data.alternate_contacts.forEach(contact => {
            if (contact.name && contact.name.trim() && contact.name !== 'Email') {
                let contactLine = `${contact.type || 'Contact'}: ${contact.name}`;
                if (contact.phone && contact.phone.trim()) {
                    contactLine += ` (${contact.phone})`;
                    // Collect unique phone numbers
                    if (!allAvailablePhones.includes(contact.phone)) {
                        allAvailablePhones.push(contact.phone);
                    }
                }
                if (contact.email && contact.email.trim()) {
                    contactLine += ` - ${contact.email}`;
                }
                contactTexts.push(contactLine);
            }
        });
        
        // Add extra phones that aren't already in the list
        extraPhones.forEach(phone => {
            if (phone && !allAvailablePhones.includes(phone)) {
                allAvailablePhones.push(phone);
            }
        });
        
        // Enhanced phone assignment logic for distinct numbers
        console.log('Available phones before assignment:', allAvailablePhones);
        
        if (allAvailablePhones.length >= 2) {
            phone3 = allAvailablePhones[0];
            phone4 = allAvailablePhones[1];
        } else if (allAvailablePhones.length === 1) {
            phone3 = allAvailablePhones[0];
            // Try to get a different phone from the main phone data
            const mainPhones = [data.phone, data.mobile, data.home_phone, data.work_phone].filter(p => p && p !== phone3);
            if (mainPhones.length > 0) {
                phone4 = mainPhones[0];
            } else {
                phone4 = ''; // Leave empty if no distinct number
            }
        } else {
            // Fallback to main phone data if no alternate contact phones
            const mainPhones = [data.phone, data.mobile, data.home_phone, data.work_phone].filter(p => p);
            if (mainPhones.length >= 2) {
                phone3 = mainPhones[0];
                phone4 = mainPhones[1];
            } else if (mainPhones.length === 1) {
                phone3 = mainPhones[0];
                phone4 = '';
            }
        }
        
        console.log('PHONE ASSIGNMENT DEBUG v2.0:', {
            allAvailablePhones,
            phone3,
            phone4,
            extraPhones: data.extra_phones,
            mainPhoneData: {
                phone: data.phone,
                mobile: data.mobile,
                home_phone: data.home_phone,
                work_phone: data.work_phone
            }
        });
        
        allContactsText = contactTexts.join('; ');
    }
    
    // Populate the Best Contact field with all contact information
    document.getElementById('alternate-contact-name').value = allContactsText;
    
    // Phone 3 and Phone 4 fields with distinct numbers
    document.getElementById('alternate-contact-phone').value = phone3;  // Phone 3
    document.getElementById('alternate-contact-phone2').value = phone4;  // Phone 4
    
    // Also populate the hidden PDF phone fields for payload service
    document.getElementById('pdf_phone3').value = phone3;
    document.getElementById('pdf_phone4').value = phone4;
    
    // Email from the primary contact
    const primaryContact = data.alternate_contacts ? data.alternate_contacts[0] : null;
    if (document.getElementById('alternate-contact-email')) {
        document.getElementById('alternate-contact-email').value = primaryContact ? primaryContact.email || '' : '';
    }

    // Store all alternates for export
    window._lastExtractedAlternateContacts = data.alternate_contacts || [];

    // Update prefix for secondary PO based on actual job number
    if (document.getElementById('secondary-po-prefix')) document.getElementById('secondary-po-prefix').textContent = (data.actual_job_number || '') + '-';
}

/**
 * Setup logic for Builder Search functionality
 */
function setupBuilderSearch() {
    const searchBtn = document.getElementById('sold-to-search-btn');
    const searchField = document.getElementById('sold-to-search');
    const resultsDiv = document.getElementById('sold-to-results');
    // Add or get loading indicator
    let loadingIndicator = document.getElementById('builder-search-loading');
    if (!loadingIndicator) {
        loadingIndicator = document.createElement('span');
        loadingIndicator.id = 'builder-search-loading';
        loadingIndicator.className = 'ml-2 text-atoz-yellow';
        loadingIndicator.style.display = 'none';
        loadingIndicator.innerHTML = '<svg class="animate-spin h-3 w-3 text-yellow-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path></svg>';
        searchBtn.parentNode.appendChild(loadingIndicator);
    }
    if (searchBtn) {
        searchBtn.addEventListener('click', async function() {
            const searchTerm = searchField.value;
            loadingIndicator.style.display = '';
            resultsDiv.innerHTML = '';
            try {
                const response = await fetchWithRetry('/api/customers/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ term: searchTerm })
            });
                const customers = await response.json();
                if (customers.error) {
                    resultsDiv.innerHTML = `<p class="text-red-500">Error: ${customers.error}</p>`;
                    return;
            }
                if (!customers.length) {
                    resultsDiv.innerHTML = '<p class="text-gray-500">No customers found</p>';
                    return;
        }
                // Display results
                let html = '<div class="space-y-2">';
                customers.forEach(customer => {
                    html += `
                        <div class="border border-gray-600 rounded p-2 hover:bg-gray-700 cursor-pointer customer-result" 
                             data-id="${customer.id || customer.customer_source_id}"
                             data-customer='${JSON.stringify(customer).replace(/'/g, "&apos;")}' >
                            <p class="font-medium">${customer.name || customer.business_name || customer.first_name + ' ' + customer.last_name}</p>
                            <p class="text-sm text-gray-400">${customer.address1 || ''}, ${customer.city || ''}</p>
                            <p class="text-sm text-gray-400">ID: ${customer.id || customer.customer_source_id}</p>
                        </div>
                    `;
    });
                html += '</div>';
                resultsDiv.innerHTML = html;
                // Add click handlers to results
                document.querySelectorAll('.customer-result').forEach(item => {
                    item.addEventListener('click', function() {
                        const customerId = this.dataset.id;
                        const customerData = JSON.parse(this.dataset.customer);
                        // Populate sold-to fields
                        document.getElementById('sold-to-rfms-id').value = customerId;
                        document.getElementById('sold-to-name').value = customerData.name || 
                            `${customerData.first_name || ''} ${customerData.last_name || ''}`.trim();
                        document.getElementById('sold-to-business-name').value = customerData.business_name || '';
                        document.getElementById('sold-to-address1').value = customerData.address1 || '';
                        document.getElementById('sold-to-address2').value = customerData.address2 || '';
                        document.getElementById('sold-to-city').value = customerData.city || '';
                        document.getElementById('sold-to-state').value = customerData.state || '';
                        document.getElementById('sold-to-zip').value = customerData.zip_code || '';
                        document.getElementById('sold-to-phone1').value = customerData.phone || '';
                        document.getElementById('sold-to-phone2').value = customerData.phone2 || '';
                        const emailField = document.getElementById('sold-to-email');
                        if (emailField) emailField.value = customerData.email || '';
                        // Clear results
                        resultsDiv.innerHTML = '<p class="text-green-500">Customer selected</p>';
                    });
                });
            } catch (error) {
                console.error('Search error:', error);
                resultsDiv.innerHTML = '<div class="text-red-500">Search failed: ' + error.message + '</div>';
            } finally {
                loadingIndicator.style.display = 'none';
            }
        });
    }
}

/**
 * Setup logic for Add Customer and Create Job buttons
 */
function setupAddCustomerAndCreateJob() {
    const addCustomerButton = document.getElementById('add-customer-button');
    const createJobButton = document.getElementById('create-job-button');
    if (!addCustomerButton || !createJobButton) return;
    let createdCustomerId = null;
    createJobButton.disabled = true;

    // Helper to reset job creation state
    function resetJobCreationState() {
        createdCustomerId = null;
        createJobButton.disabled = true;
    }

    // Reset state when form is cleared or PDF is uploaded
    const clearTriggers = [
        document.getElementById('upload-button'),
        document.getElementById('pdf-upload'),
        document.getElementById('clear-form-button')
    ];
    clearTriggers.forEach(el => {
        if (el) {
            el.addEventListener('click', resetJobCreationState);
        }
    });

    addCustomerButton.addEventListener('click', async () => {
        // Gather Ship To data
        const shipTo = {
            first_name: document.getElementById('ship-to-first-name')?.value || '',
            last_name: document.getElementById('ship-to-last-name')?.value || '',
            address1: document.getElementById('ship-to-address1').value || '',
            address2: document.getElementById('ship-to-address2').value || '',
            city: document.getElementById('ship-to-city').value || '',
            state: document.getElementById('ship-to-state')?.value || '',
            zip_code: document.getElementById('ship-to-zip').value || '',
            county: document.getElementById('ship-to-county')?.value || '',
            phone: document.getElementById('pdf-phone1').value || '',  // Use PDF Phone 1
            phone2: document.getElementById('pdf-phone2').value || '', // Use PDF Phone 2
            email: document.getElementById('ship-to-email').value || '',
            customer_type: 'INSURANCE',
            business_name: document.getElementById('ship-to-business-name')?.value || ''
        };
        // Ensure required fields are present (even if empty)
        shipTo.business_name = shipTo.business_name || '';
        shipTo.first_name = shipTo.first_name || '';
        shipTo.last_name = shipTo.last_name || '';
        shipTo.state = shipTo.state || '';
        addCustomerButton.disabled = true;
        addCustomerButton.textContent = 'Processing...';
        try {
            const response = await fetchWithRetry('/api/create_customer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(shipTo)
            });
            const result = await response.json();
            console.log('[DEBUG] Customer creation response:', result);
            
            // Handle different possible response structures from RFMS
            let customerId = null;
            
            // Check if customer already exists (RFMS returns this when duplicate found)
            if (result && result.status === 'failed' && result.detail && result.detail.existingCustomerId) {
                customerId = result.detail.existingCustomerId;
                createdCustomerId = customerId;
                showNotification(`Customer already exists in RFMS! Using existing ID: ${customerId}`, 'info');
                createJobButton.disabled = false;
            } else if (result) {
                // Try different possible fields for customer ID (new customer)
                customerId = result.id || result.customerId || result.customerSeqNum || 
                           result.result?.id || result.result?.customerId || result.result?.customerSeqNum ||
                           result.data?.id || result.data?.customerId || result.data?.customerSeqNum;
                
                if (customerId) {
                    createdCustomerId = customerId;
                    showNotification(`Customer created in RFMS! ID: ${customerId}`, 'success');
                createJobButton.disabled = false;
            } else {
                    // Even if we don't get an ID, if the response is successful, consider it created
                    if (result && !result.error && response.ok && result.status !== 'failed') {
                        createdCustomerId = 'CREATED'; // Placeholder ID
                        showNotification('Customer created in RFMS! (ID not returned)', 'success');
                        createJobButton.disabled = false;
                    } else {
                        console.error('[DEBUG] Customer creation failed:', result);
                        showNotification(`Failed to create customer: ${result.result || 'Unknown error'}`, 'error');
                        createJobButton.disabled = true;
                    }
                }
            } else {
                console.error('[DEBUG] No response from customer creation');
                showNotification('Failed to create customer in RFMS.', 'error');
                createJobButton.disabled = true;
            }
        } catch (error) {
            handleApiError(error, 'creating customer in RFMS');
            createJobButton.disabled = true;
        } finally {
            addCustomerButton.disabled = false;
            addCustomerButton.textContent = 'Add Customer';
        }
    });

    createJobButton.addEventListener('click', async () => {
        if (!createdCustomerId) {
            showNotification('Please add the customer to RFMS first.', 'warning');
            createJobButton.disabled = true;
            return;
        }
        // Gather Sold To data with debugging
        console.log('[DEBUG] Gathering form data...');
        
        const soldToNameEl = document.getElementById('sold-to-name');
        const soldToCustomerIdEl = document.getElementById('sold-to-rfms-id');
        const shipToNameEl = document.getElementById('ship-to-name');
        const poNumberEl = document.getElementById('po-number');
        
        console.log('[DEBUG] Form elements found:', {
            soldToName: !!soldToNameEl,
            soldToCustomerId: !!soldToCustomerIdEl,
            shipToName: !!shipToNameEl,
            poNumber: !!poNumberEl
        });
        
        if (!soldToNameEl || !shipToNameEl || !poNumberEl) {
            console.error('[DEBUG] Missing required form elements!');
            showNotification('Form validation error - missing required fields', 'error');
            return;
        }
        
        const soldToName = soldToNameEl.value.trim();
        const soldToCustomerId = soldToCustomerIdEl ? soldToCustomerIdEl.value.trim() : '';
        const shipToName = shipToNameEl.value.trim();
        const poNumber = poNumberEl.value.trim();
        const missingFields = [];
        if (!soldToName) missingFields.push('Builder Name');
        if (!soldToCustomerId) missingFields.push('Builder ID');
        if (!shipToName) missingFields.push('Ship To Name');
        if (!poNumber) missingFields.push('PO Number');
        if (missingFields.length > 0) {
            showNotification(`Please complete the following required fields: ${missingFields.join(', ')}`, 'warning');
            return;
        }
        const soldTo = {
            id: soldToCustomerId,
            name: soldToName,
            address1: document.getElementById('sold-to-address1')?.value || '',
            address2: document.getElementById('sold-to-address2')?.value || '',
            city: document.getElementById('sold-to-city')?.value || '',
            zip_code: document.getElementById('sold-to-zip')?.value || '',
            country: document.getElementById('sold-to-country')?.value || 'Australia',
            phone: document.getElementById('sold-to-phone')?.value || '',
            email: document.getElementById('sold-to-email')?.value || ''
        };
        const shipTo = {
            name: shipToName,
            address1: document.getElementById('ship-to-address1')?.value || '',
            address2: document.getElementById('ship-to-address2')?.value || '',
            city: document.getElementById('ship-to-city')?.value || '',
            zip_code: document.getElementById('ship-to-zip')?.value || '',
            country: document.getElementById('ship-to-country')?.value || 'Australia',
            phone1: document.getElementById('ship-to-phone1')?.value || '',  // Phone 1 from UI
            phone2: document.getElementById('ship-to-phone2')?.value || '',  // Phone 2 from UI
                            pdf_phone1: document.getElementById('pdf-phone1')?.value || '',  // PDF Phone 1
                pdf_phone2: document.getElementById('pdf-phone2')?.value || '',  // PDF Phone 2
                pdf_phone3: document.getElementById('pdf_phone3')?.value || '',  // Phone 3 (Authorised Contact)
                pdf_phone4: document.getElementById('pdf_phone4')?.value || '',  // Phone 4 (Site Contact)
            email: document.getElementById('ship-to-email')?.value || '',
            id: createdCustomerId
        };
        const altContact = {
            name: document.getElementById('alternate-contact-name')?.value || '',
            phone: document.getElementById('alternate-contact-phone')?.value || '',
            phone2: document.getElementById('alternate-contact-phone2')?.value || '',
            email: document.getElementById('alternate-contact-email')?.value || ''
        };
        let descriptionOfWorks = document.getElementById('description-of-works').value;
        if (altContact.name || altContact.phone || altContact.phone2 || altContact.email) {
            let bestContactStr = `Best Contact: ${altContact.name || ''} ${altContact.phone || ''}`;
            if (altContact.phone2) bestContactStr += `, ${altContact.phone2}`;
            if (altContact.email) bestContactStr += ` (${altContact.email})`;
            descriptionOfWorks += `\n${bestContactStr}`;
        }
        const jobDetails = {
            job_number: document.getElementById('supervisor-phone')?.value || '',
            actual_job_number: document.getElementById('actual-job-number')?.value || '',
            po_number: poNumber,
            description_of_works: descriptionOfWorks,
            dollar_value: parseFloat(document.getElementById('dollar-value')?.value || '0') || 0,
            supervisor_name: document.getElementById('supervisor-name')?.value || '',
            supervisor_phone: document.getElementById('supervisor-phone')?.value || ''
        };
        const billingGroup = {};
        const billingGroupCheckbox = document.getElementById('billing-group-checkbox');
        if (billingGroupCheckbox && billingGroupCheckbox.checked) {
            billingGroup.is_billing_group = true;
            billingGroup.po_suffix = document.getElementById('secondary-po-suffix')?.value || '';
            billingGroup.second_value = parseFloat(document.getElementById('second-po-dollar-value')?.value || '0') || 0;
        }
        const payload = {
            sold_to: soldTo,
            ship_to: shipTo,
            job_details: jobDetails,
            billing_group: billingGroup,
            alternate_contact: altContact,
            alternate_contacts: window._lastExtractedAlternateContacts || []
        };
        createJobButton.disabled = true;
        createJobButton.textContent = 'Processing...';
        const loadingNotification = showNotification('Creating job in RFMS...', 'info', 0);
        try {
            const response = await fetchWithRetry('/api/export-to-rfms', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            showNotification('Job created in RFMS!', 'success');
            if (result.job_id) {
                showNotification(`Job created with ID: ${result.job_id}`, 'success', 5000);
            }
        } catch (error) {
            handleApiError(error, 'creating job in RFMS');
        } finally {
            createJobButton.disabled = false;
            createJobButton.textContent = 'Create Job';
            const persistentNotification = document.getElementById('notification-loading');
            if (persistentNotification) {
                document.body.removeChild(persistentNotification);
            }
        }
    });
}

/**
 * Clear best contact fields
 */
function clearBestContacts() {
    const bestContactFields = [
        'alternate-contact-name',
        'alternate-contact-phone',
        'alternate-contact-phone2',
        'alternate-contact-email'
    ];
    
    bestContactFields.forEach(id => {
        const field = document.getElementById(id);
        if (field) field.value = '';
    });
}

// Find the create job button and description of works field
const createJobButton = document.getElementById('create-job-button');
const descriptionOfWorksField = document.getElementById('description-of-works');

function validateDescriptionOfWorks() {
    const value = descriptionOfWorksField.value.trim();
    const wordCount = value.split(/\s+/).filter(Boolean).length;
    if (wordCount < 5) {
        createJobButton.disabled = true;
        showNotification("General Scope of Works required!  example: Restrectch carpet back in bedroom two or Floor preperation PO for adding to billing group", 'error');
        return false;
    } else {
        createJobButton.disabled = false;
        return true;
    }
}

// Add event listener to validate on input
if (descriptionOfWorksField && createJobButton) {
    descriptionOfWorksField.addEventListener('input', validateDescriptionOfWorks);
}

// Also validate when the Create Job button is clicked
if (createJobButton) {
    createJobButton.addEventListener('click', function(e) {
        if (!validateDescriptionOfWorks()) {
            e.preventDefault();
            return false;
        }
    });
}

function enforceBuilderSelectionBeforeUpload() {
    console.log('[DEBUG] Setting up builder selection validation...');
    const uploadBtn = document.getElementById('upload-pdf-btn');
    const builderNameField = document.getElementById('sold-to-name');
    
    if (!uploadBtn || !builderNameField) {
        console.error('[DEBUG] Required elements not found:', {
            uploadBtn: !!uploadBtn,
            builderNameField: !!builderNameField
        });
        return;
    }

    function checkBuilderSelected() {
        const builderSelected = builderNameField.value && builderNameField.value.trim().length > 0;
        console.log('[DEBUG] Builder selection check:', {
            builderValue: builderNameField.value,
            isSelected: builderSelected
        });
        uploadBtn.disabled = !builderSelected;
        if (!builderSelected) {
            showNotification('Please select a builder before uploading a PDF', 'warning');
        }
    }

    // Initial check
    checkBuilderSelected();

    // Listen for changes in the builder name field
    builderNameField.addEventListener('input', checkBuilderSelected);
    // If builder is selected via search, also check
    builderNameField.addEventListener('change', checkBuilderSelected);
    
    // Also check when the builder is selected via the search results
    const searchResults = document.getElementById('sold-to-results');
    if (searchResults) {
        searchResults.addEventListener('click', function(e) {
            // Wait a short moment for the builder name to be populated
            setTimeout(checkBuilderSelected, 100);
        });
    }
    
    console.log('[DEBUG] Builder selection validation setup complete');
} 