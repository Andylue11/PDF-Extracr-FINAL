# Order Mapping Structure

## Main Fields

| Field | Value | Source |
|-------|-------|--------|
| category | Order | Fixed (hardcoded) |
| poNumber | PO_NUMBER | PDF extracted data, verified in UI |
| jobNumber | SUPERVISOR NAME & SUPERVISOR PHONE/MOBILE | PDF extracted data, verified in UI |
| storeNumber | 49 | Fixed (hardcoded) |
| salesperson1 | ZORAN VEKIC | Preferred salesperson data selected & verified in UI (fallback default option) |
| salesperson2 | "" | Fixed (hardcoded) |

## Sold To Information

| Field | Value | Source |
|-------|-------|--------|
| customerType | BUILDERS | Fixed (hardcoded) |
| customerId | customerId | CustomerID data verified in UI |
| firstName | PROFILE BILL GROUP | Data verified in UI |
| lastName | PROFILE BILL GROUP | Data verified in UI |
| address1 | 23 MAYNEVIEW STREET | Data verified in UI |
| address2 | "" | Data verified in UI |
| city | MILTON | Data verified in UI |
| state | QLD | Data verified in UI |
| postalCode | 4064 | Data verified in UI |
| phone1 | SHIPTO_PHONE3 | PDF extracted data, verified in UI (fallback: SOLDTO_PHONE1) |
| phone2 | SHIPTO_PHONE4 | PDF extracted data, verified in UI (fallback: SOLDTO_PHONE2) |
| email | SHIPTO_EMAIL | PDF extracted data, verified in UI (fallback: "accounts@atozflooringsolutions.com.au") |

## Ship To Information

| Field | Value | Source |
|-------|-------|--------|
| firstName | Site | PDF extracted data, verified in UI |
| lastName | Customer | PDF extracted data, verified in UI |
| address1 | 1505 ROSEBANK WAY WEST | PDF extracted data, verified in UI |
| address2 | "" | PDF extracted data, verified in UI |
| city | HOPE ISLAND | PDF extracted data, verified in UI |
| state | QLD | PDF extracted data, verified in UI |
| postalCode | 4212 | PDF extracted data, verified in UI |

## Additional Fields

| Field | Value | Source |
|-------|-------|--------|
| privateNotes | SITE CONTACT, ALTERNATE CONTACT, OTHER CONTACTS, PHONE1, PHONE2 | PDF extracted data, verified in UI |
| publicNotes | JOB DISCRIPTION, WORKS REQUIRED, SCOPE OF WORKS | PDF extracted data, verified in UI |
| workOrderNotes | SITE CONTACT, ALTERNATE CONTACT, PHONE1, PHONE2 | PDF extracted data, verified in UI |
| measureDate | COMMENCE_DATE, START DATE, BOOKED DATE | PDF extracted data, verified in UI |
| estimatedDeliveryDate | COMPLETION_DATE | PDF extracted data, verified in UI (>5DAYS) |
| priceLevel | 3 | Fixed (hardcoded) |
| Occupied | true | Fixed (hardcoded) |
| userOrderTypeId | 18 | Fixed (hardcoded) |
| serviceTypeId | 8 | Fixed (hardcoded) |
| contractTypeId | 1 | Fixed (hardcoded) |
| adSourceId | 1 | Fixed (hardcoded) |

## Line Items

| Field | Value | Source |
|-------|-------|--------|
| id | "" | Fixed (hardcoded) |
| isUseTaxLine | false | Fixed (hardcoded) |
| productId | 213322 | Fixed (hardcoded) |
| colorId | 2133 | Fixed (hardcoded) |
| quantity | DOLLAR_VALUE | PDF extracted data, verified in UI |
| priceLevel | 10 | Fixed (hardcoded) |
| lineStatus | none | Fixed (hardcoded) |
| lineGroupId | 4 | Fixed (hardcoded) | 