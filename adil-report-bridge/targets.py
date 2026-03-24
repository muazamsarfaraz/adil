"""Target form configurations for the report bridge.

Each target defines a reporting portal with its URL, AI agent instructions,
and required/optional field lists. Adding a new target = adding a dict entry.
"""
from typing import Optional, Dict, List, Any

TARGETS: Dict[str, Dict[str, Any]] = {
    "police-uk": {
        "adapter_type": "browser",
        "name": "Police UK — National Hate Crime Report",
        "url": "https://www.police.uk/ro/report/hate-crime/forms/v1/hate-crime-online2/",
        "instructions": (
            "Fill the multi-step hate crime reporting form with the provided data. "
            "Step 1: Enter personal details (first name, surname, date of birth, gender). "
            "Step 2: Enter contact details (email, phone, address). "
            "Step 3: Select role (victim, witness, or third party). "
            "Step 4: Enter incident details (what happened, where, when). "
            "Step 5: Add any evidence or URLs. "
            "Step 6: Enter suspect description if provided. "
            "Step 7: Review all details and submit. "
            "Always add 'Submitted via AskAdil (askadil.org) on behalf of the reporter' "
            "in the additional information field. "
            "After submission, capture the confirmation page including any reference number."
        ),
        "required_fields": [
            "first_name", "surname", "dob", "gender", "email",
            "incident_details", "location", "date_time",
        ],
        "optional_fields": [
            "phone", "address", "role", "suspect_description",
            "additional_info", "evidence_urls",
        ],
        "coverage": "England & Wales",
    },
    "tell-mama": {
        "adapter_type": "browser",
        "name": "Tell MAMA — Report Anti-Muslim Hate",
        "url": "https://tellmamauk.org/submit-a-report-to-us/",
        "instructions": (
            "Fill the Tell MAMA hate crime reporting form with the provided data. "
            "This is a single-page WordPress form (WPForms/CF7). "
            "Fill in: Name, Email, Phone (with UK +44 country code), "
            "tick the appropriate incident type checkboxes (Abusive Behaviour, Threatening Behaviour, "
            "Assault, Vandalism, Discrimination, Hate Speech, Anti-Muslim Literature, Online content or abuse), "
            "Date and Time of incident, Description of incident, Location fields "
            "(Address Line 1, City, Postal Code, select 'United Kingdom' as country), "
            "upload photo/video evidence if provided, "
            "select whether victim or witness, "
            "fill in victim demographics (Gender, Age Group, Ethnicity) if provided, "
            "fill in perpetrator details (Gender, Age Group, Ethnicity) if provided, "
            "select 'Other' for 'How did you hear about us', "
            "then click Submit. "
            "Always add 'Submitted via AskAdil (askadil.org)' in the description field. "
            "After submission, capture the confirmation page."
        ),
        "required_fields": [
            "first_name", "surname", "email", "phone",
            "incident_type", "incident_details", "location",
        ],
        "optional_fields": [
            "date_time", "gender", "age_group", "ethnicity",
            "suspect_gender", "suspect_age_group", "suspect_ethnicity",
            "role", "evidence_urls", "additional_info",
        ],
        "coverage": "United Kingdom",
    },
    "police-scotland": {
        "adapter_type": "browser",
        "name": "Police Scotland — Hate Crime Report",
        "url": "https://www.scotland.police.uk/secureforms/c3/",
        "instructions": (
            "Fill the Police Scotland hate crime reporting form with the provided data. "
            "This is a single-page form with conditional panels. "
            "Select 'No' for emergency (unless indicated otherwise). "
            "Select 'Hate Related Incident - Religion' as incident type. "
            "Select whether reporting for self or third party based on role field. "
            "Fill in personal details: Name, Address, Town, Postcode, Phone, Email. "
            "Fill in the 5 narrative sections (each up to 2000 chars): "
            "1. What happened - use incident_details, "
            "2. Where did this happen - use location, "
            "3. When did this happen - use date_time, "
            "4. Description of person - use suspect_description or 'Unknown', "
            "5. Additional info - include 'Submitted via AskAdil (askadil.org) on behalf of the reporter'. "
            "Tick the disclaimer checkbox and submit. "
            "After submission, capture the confirmation page including any reference number."
        ),
        "required_fields": [
            "first_name", "surname", "email", "phone",
            "incident_details", "location", "date_time",
        ],
        "optional_fields": [
            "address", "postcode", "town", "dob", "role",
            "suspect_description", "additional_info", "evidence_urls",
        ],
        "coverage": "Scotland",
    },
    "iru": {
        "adapter_type": "browser",
        "name": "IRU — Islamophobia Response Unit",
        "url": "https://www.theiru.org.uk/report-islamophobia/",
        "instructions": (
            "Fill the IRU Islamophobia reporting form with the provided data. "
            "This is a single-page form with conditional panels. "
            "Contact Details section: Fill in Full Name, Email Address, Phone Number. "
            "Personal Details section: Select Gender, fill Ethnicity, Country of Residence (select 'United Kingdom'), "
            "enter Age. If age is under 18, a parental consent section appears — skip if over 18. "
            "Incident Details section: Select 'I'm the victim' or 'On behalf of someone else' based on role field. "
            "Fill in Date of incident, Location of Incident, and Incident Details (the main narrative). "
            "Further Information section: Select 'Yes' or 'No' for police report status, "
            "select 'No' for CCTV awareness (unless specified), "
            "select 'No' for referred by organisation (unless specified), "
            "select 'No' for contacted other organisations (unless specified), "
            "leave court dates blank unless specified. "
            "Tick the consent checkbox. "
            "Add 'Submitted via AskAdil (askadil.org) on behalf of the reporter' at the end of Incident Details. "
            "Click 'Submit your report'. "
            "After submission, capture the confirmation page."
        ),
        "required_fields": [
            "first_name", "surname", "email", "phone",
            "gender", "country", "age",
            "incident_details", "location",
        ],
        "optional_fields": [
            "ethnicity", "date_time", "role",
            "police_reported", "additional_info",
        ],
        "coverage": "United Kingdom",
    },
    "islamophobia-uk": {
        "adapter_type": "browser",
        "name": "Islamophobia UK — Incident Tracker",
        "url": "https://islamophobiauk.co.uk/",
        "instructions": (
            "Fill the Islamophobia UK incident report form on the homepage. "
            "The form is embedded on the main page — look for the 'Report Incident' section. "
            "Fill in: Brief summary of the incident (short summary field), "
            "Location (city, area, or specific location), "
            "Date of Incident (date picker), "
            "Time of Incident (dropdown selector), "
            "Factual description (detailed description textarea), "
            "Victim's Ethnicity (optional dropdown — select if provided), "
            "Incident Type (dropdown — select the most relevant type e.g. 'Verbal Abuse', 'Physical Attack', 'Online Hate'). "
            "Add 'Submitted via AskAdil (askadil.org)' at the end of the factual description. "
            "Click the submit button. "
            "Note: This form does NOT require personal details (no name, email, or phone). "
            "After submission, capture the confirmation or any response shown."
        ),
        "required_fields": [
            "incident_summary", "incident_details", "location",
        ],
        "optional_fields": [
            "date_time", "time_of_incident", "ethnicity",
            "incident_type", "additional_info",
        ],
        "coverage": "United Kingdom",
    },
    # --- Email adapter targets ---
    "eass": {
        "adapter_type": "email",
        "name": "EASS — Equality Advisory Support Service",
        "url": "https://equalityadvisoryservice.com",
        "email_to": "correspondence@equalityadvisoryservice.com",
        "email_subject": "Discrimination Enquiry via AskAdil",
        "required_fields": [
            "first_name", "surname", "email",
            "incident_details",
        ],
        "optional_fields": [
            "phone", "location", "date_time",
            "suspect_description", "additional_info",
        ],
        "coverage": "England, Wales & Scotland",
    },
    "stop-hate-uk": {
        "adapter_type": "email",
        "name": "Stop Hate UK",
        "url": "https://stophateuk.org",
        "email_to": "talk@stophateuk.org",
        "email_subject": "Hate Incident Report via AskAdil",
        "required_fields": [
            "first_name", "surname", "email",
            "incident_details", "location",
        ],
        "optional_fields": [
            "phone", "date_time",
            "suspect_description", "additional_info",
        ],
        "coverage": "United Kingdom",
    },
}


def get_target(target_id: str) -> Optional[Dict[str, Any]]:
    """Return target config or None if not found."""
    return TARGETS.get(target_id)


def validate_data_for_target(target_id: str, data: Dict[str, Any]) -> List[str]:
    """Return list of missing required fields for the given target."""
    target = get_target(target_id)
    if not target:
        return [f"Unknown target: {target_id}"]
    return [f for f in target["required_fields"] if f not in data or not data[f]]
