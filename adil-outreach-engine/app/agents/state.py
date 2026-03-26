from typing import TypedDict


class OutreachState(TypedDict):
    # Identifiers
    contact_id: str
    campaign_id: str

    # Full records (loaded at graph start)
    contact: dict  # contact record from DB
    campaign: dict  # campaign config from DB

    # Research output
    research_data: dict  # populated by research node — personalisation hooks, SRA status, key info

    # Compose output
    draft_subject: str  # populated by compose node
    draft_body: str  # populated by compose node

    # Reply handling
    reply_text: str  # populated when reply received (from inbound webhook)
    classification: str  # populated by classify node — one of: interested, declined, question, out_of_office, bounce

    # Graph state tracking
    current_step: str  # current node name in the graph
    error: str  # last error message if any
