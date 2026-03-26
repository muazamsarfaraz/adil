from pydantic import BaseModel


class CampaignStats(BaseModel):
    total_contacts: int = 0
    pending: int = 0
    researching: int = 0
    ready: int = 0
    draft_pending: int = 0
    emailed: int = 0
    replied: int = 0
    converted: int = 0
    declined: int = 0
    unresponsive: int = 0
    bounced: int = 0
    open_rate: float = 0.0
    reply_rate: float = 0.0
    conversion_rate: float = 0.0
