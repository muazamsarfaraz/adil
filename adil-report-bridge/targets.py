"""Target form configurations for the report bridge.

Each target defines a reporting portal with its URL, AI agent instructions,
and required/optional field lists. Adding a new target = adding a dict entry.
"""

from typing import Any

TARGETS: dict[str, dict[str, Any]] = {
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
            "first_name",
            "surname",
            "dob",
            "gender",
            "email",
            "incident_details",
            "location",
            "date_time",
        ],
        "optional_fields": [
            "phone",
            "address",
            "role",
            "suspect_description",
            "additional_info",
            "evidence_urls",
        ],
        "coverage": "England & Wales",
    },
    "tell-mama": {
        "adapter_type": "browser",
        "name": "Tell MAMA — Report Anti-Muslim Hate",
        "url": "https://tellmamauk.org/submit-a-report-to-us/",
        "instructions": (
            "Fill the Tell MAMA hate crime reporting form with the provided data. "
            "This is a single-page WordPress form. "
            "Fill in: Name, Email, Phone (with UK +44 country code). "
            "Tick the appropriate incident type checkboxes (Abusive Behaviour, Threatening Behaviour, "
            "Assault, Vandalism, Discrimination, Hate Speech, Anti-Muslim Literature, Online content or abuse). "
            "Date and Time of incident, Description of incident. "
            "Location fields: Address Line 1, City, State/Province/Region, Postal Code, "
            "select 'United Kingdom' as country. "
            "Upload photo/video evidence if provided (max 5 files, 25 MB each). "
            "Select role: 'Yes' (victim), 'No, I am a witness', or "
            "'No, I am reporting on behalf of someone else'. "
            "Fill in victim demographics (Gender: Male/Female/Non-binary/Other/Unknown, "
            "Age Group dropdown, Ethnicity dropdown with UK census categories) if provided. "
            "Fill in perpetrator details (Gender — includes 'Multiple/Group' option, "
            "Age Group, Ethnicity) if provided. "
            "Select 'Other' for 'How did you hear about us'. "
            "Click Submit. "
            "Always add 'Submitted via AskAdil (askadil.org)' in the description field. "
            "After submission, capture the confirmation page."
        ),
        "required_fields": [
            "first_name",
            "surname",
            "email",
            "phone",
            "incident_type",
            "incident_details",
            "location",
        ],
        "optional_fields": [
            "date_time",
            "gender",
            "age_group",
            "ethnicity",
            "suspect_gender",
            "suspect_age_group",
            "suspect_ethnicity",
            "role",
            "evidence_urls",
            "additional_info",
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
            "first_name",
            "surname",
            "email",
            "phone",
            "incident_details",
            "location",
            "date_time",
        ],
        "optional_fields": [
            "address",
            "postcode",
            "town",
            "dob",
            "role",
            "suspect_description",
            "additional_info",
            "evidence_urls",
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
            "Personal Details section: Select Gender (Male/Female/Other — if Other, fill the 'Other' text field), "
            "fill Ethnicity, Country of Residence (select 'United Kingdom'), enter Age. "
            "If age is under 18, a parental consent section appears — fill Parent/Guardian Full Name, "
            "Relation, Email Address, and Phone Number. Skip if over 18. "
            "Incident Details section: Select 'I'm the victim' or 'On behalf of someone else'. "
            "If 'On behalf of someone else': fill Victim's Full Name, Victim's Age, "
            "Victim's Gender, and Your relationship with the victim. "
            "Fill in Date of incident, Location of Incident, and Incident Details (the main narrative). "
            "Further Information section: Select 'Yes' or 'No' for police report status, "
            "select 'No' for CCTV awareness (unless specified), "
            "select 'No' for referred by organisation (unless specified — if Yes, provide org details), "
            "select 'No' for contacted other organisations (unless specified — if Yes, provide org details), "
            "leave court dates blank unless specified. "
            "Tick the consent checkbox. Optionally tick 'Please send me a copy' to email a copy of the report. "
            "Add 'Submitted via AskAdil (askadil.org) on behalf of the reporter' at the end of Incident Details. "
            "Click 'Submit your report'. "
            "After submission, capture the confirmation page."
        ),
        "required_fields": [
            "first_name",
            "surname",
            "email",
            "phone",
            "gender",
            "country",
            "age",
            "incident_details",
            "location",
        ],
        "optional_fields": [
            "ethnicity",
            "date_time",
            "role",
            "police_reported",
            "cctv_aware",
            "referred_by_org",
            "contacted_other_org",
            "court_dates",
            "victim_name",
            "victim_age",
            "victim_gender",
            "victim_relationship",
            "guardian_name",
            "guardian_relation",
            "guardian_email",
            "guardian_phone",
            "additional_info",
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
            "incident_summary",
            "incident_details",
            "location",
        ],
        "optional_fields": [
            "date_time",
            "time_of_incident",
            "ethnicity",
            "incident_type",
            "additional_info",
        ],
        "coverage": "United Kingdom",
    },
    "british-muslim-trust": {
        "adapter_type": "browser",
        "name": "British Muslim Trust — Report Anti-Muslim Hate",
        "url": "https://britishmuslimtrust.co.uk/report-hate",
        "instructions": (
            "Fill the British Muslim Trust 3-step Salesforce form embedded in an iframe "
            "(src: britishmuslimtrust.my.site.com/ReportIncident/). The form is inside a "
            "shadow DOM component <c-report-incident>. "
            "Step 1 — About You: "
            "Select 'I'm reporting as' (options: I was the victim of the incident, "
            "I witnessed the incident, Reporting on behalf of someone else, Other). "
            "Select 'Victim's Gender' (Male, Female, Other, Prefer Not To Say, Unknown). "
            "Select 'Victim's Ethnicity' from UK census categories dropdown. "
            "Fill 'Victim's Name' (text), 'Victim's Age' (number, optional), "
            "'Phone' (tel), 'Email Address' (text). Click Next. "
            "Step 2 — About the Incident: "
            "Tick 'Type of Incident' checkboxes (multi-select: Damage or desecration of property, "
            "Discrimination, Harassment, Threats or intimidation, Hate literature, "
            "Online abuse or harmful content, Abusive behaviour, Physical assault, Other). "
            "Fill 'Date of Incident' (DD/MM/YYYY date picker), 'Time of Incident' (hh:mm aa, optional). "
            "Fill 'Location of Incident' (textarea), select 'Location of Incident (City)' "
            "from dropdown of UK cities (includes 'Other'). "
            "Fill 'Please provide a description of what happened' (textarea). "
            "Add 'Submitted via AskAdil (askadil.org) on behalf of the reporter' at the end. "
            "Under 'Police and Case Details': select 'Have you reported this to the police?' "
            "and 'Do you have any images, documents or evidence?' if provided. Click Next. "
            "Step 3 — Review and Submit: Review all details and submit the form. "
            "After submission, capture the confirmation page including any reference number."
        ),
        "required_fields": [
            "first_name",
            "surname",
            "email",
            "phone",
            "gender",
            "incident_type",
            "incident_details",
            "location",
            "city",
            "date_time",
        ],
        "optional_fields": [
            "role",
            "age",
            "ethnicity",
            "time_of_incident",
            "police_reported",
            "has_evidence",
            "additional_info",
        ],
        "coverage": "United Kingdom",
    },
    "muslim-safety-net": {
        "adapter_type": "browser",
        "name": "Muslim Safety Net — Report Anti-Muslim Hostility",
        "url": "https://muslimsafetynet.org.uk/report",
        "instructions": (
            "Fill the Muslim Safety Net incident report form with the provided data. "
            "This is a single-page form with CAPTCHA at the bottom. "
            "Fill in contact details (name, email, phone). "
            "Fill in date, time, and location of the incident (include geographical location). "
            "Select whether reported elsewhere (police, employer, service provider). "
            "Fill in description of the incident (what happened, how, where — e.g. online, on the street, at work). "
            "Fill in offender details if provided (approximate age, sex, ethnicity). "
            "Select role: victim, reporting on behalf of victim, witness, or reporting for an organisation. "
            "Fill in personal/victim details if provided: age, ethnicity, faith, sex, immigration status, disability. "
            "Describe visible appearance markers if relevant (headscarf, clothing, beard, skin colour). "
            "Explain why the hostility was motivated by identity (religion and/or race). "
            "Select 'Other Organization' from 'How did you hear about us' dropdown. "
            "Add 'Submitted via AskAdil (askadil.org)' at the end of the incident description. "
            "Complete CAPTCHA, tick privacy policy consent, and click Submit."
        ),
        "required_fields": [
            "first_name",
            "surname",
            "email",
            "incident_details",
            "location",
        ],
        "optional_fields": [
            "phone",
            "date_time",
            "role",
            "gender",
            "age",
            "ethnicity",
            "faith",
            "disability",
            "suspect_description",
            "suspect_age",
            "suspect_ethnicity",
            "police_reported",
            "additional_info",
        ],
        "coverage": "United Kingdom",
    },
    # --- Email adapter targets ---
    "prevent-watch": {
        "adapter_type": "email",
        "name": "Prevent Watch — Prevent Duty Support",
        "url": "https://preventwatch.org/get-support/",
        "email_to": "contact@preventwatch.org",
        "email_subject": "Prevent Support Request via AskAdil",
        "required_fields": [
            "first_name",
            "surname",
            "email",
            "incident_details",
        ],
        "optional_fields": [
            "phone",
            "location",
            "date_time",
            "role",
            "additional_info",
        ],
        "coverage": "United Kingdom",
    },
    "eass": {
        "adapter_type": "email",
        "name": "EASS — Equality Advisory Support Service",
        "url": "https://www.equalityadvisoryservice.com",
        "email_to": "correspondence@equalityadvisoryservice.com",
        "email_subject": "Discrimination Enquiry via AskAdil",
        "required_fields": [
            "first_name",
            "surname",
            "email",
            "incident_details",
        ],
        "optional_fields": [
            "phone",
            "location",
            "date_time",
            "suspect_description",
            "additional_info",
        ],
        "coverage": "England, Wales & Scotland",
    },
    "stop-hate-uk": {
        "adapter_type": "email",
        "name": "Stop Hate UK",
        "url": "https://stophateuk.org/report-hate-crime/",
        "email_to": "talk@stophateuk.org",
        "email_subject": "Hate Incident Report via AskAdil",
        "required_fields": [
            "first_name",
            "surname",
            "email",
            "incident_details",
            "location",
        ],
        "optional_fields": [
            "phone",
            "date_time",
            "suspect_description",
            "additional_info",
        ],
        "coverage": "United Kingdom",
    },
}


def get_target(target_id: str) -> dict[str, Any] | None:
    """Return target config or None if not found."""
    return TARGETS.get(target_id)


def validate_data_for_target(target_id: str, data: dict[str, Any]) -> list[str]:
    """Return list of missing required fields for the given target."""
    target = get_target(target_id)
    if not target:
        return [f"Unknown target: {target_id}"]
    return [f for f in target["required_fields"] if f not in data or not data[f]]
