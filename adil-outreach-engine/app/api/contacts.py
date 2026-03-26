import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.api_key import require_api_key
from app.database import get_db
from app.models.campaign import Campaign
from app.models.contact import Contact, ContactStatus
from app.schemas.contact import (
    BulkCreateResponse,
    ContactBulkCreate,
    ContactCreate,
    ContactDetailResponse,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
)

router = APIRouter(prefix="/api/v1/outreach", tags=["contacts"], dependencies=[Depends(require_api_key)])

# Statuses that allow retry
RETRYABLE_STATUSES = {ContactStatus.unresponsive, ContactStatus.bounced, ContactStatus.declined}


@router.post("/campaigns/{campaign_id}/contacts", response_model=ContactResponse, status_code=201)
async def create_contact(campaign_id: uuid.UUID, payload: ContactCreate, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    contact = Contact(
        campaign_id=campaign_id,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        firm_name=payload.firm_name,
        website=payload.website,
        metadata_=payload.metadata,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.post("/campaigns/{campaign_id}/contacts/bulk", response_model=BulkCreateResponse, status_code=201)
async def bulk_create_contacts(campaign_id: uuid.UUID, payload: ContactBulkCreate, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    created = 0
    errors = []

    for i, contact_data in enumerate(payload.contacts):
        try:
            contact = Contact(
                campaign_id=campaign_id,
                name=contact_data.name,
                email=contact_data.email,
                phone=contact_data.phone,
                firm_name=contact_data.firm_name,
                website=contact_data.website,
                metadata_=contact_data.metadata,
            )
            db.add(contact)
            await db.flush()
            created += 1
        except Exception as e:
            errors.append({"index": i, "email": contact_data.email, "error": str(e)})

    await db.commit()
    return BulkCreateResponse(created=created, errors=errors)


@router.get("/campaigns/{campaign_id}/contacts", response_model=ContactListResponse)
async def list_contacts(
    campaign_id: uuid.UUID,
    status: ContactStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Contact).where(Contact.campaign_id == campaign_id)
    count_query = select(func.count(Contact.id)).where(Contact.campaign_id == campaign_id)

    if status:
        query = query.where(Contact.status == status)
        count_query = count_query.where(Contact.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.order_by(Contact.created_at.desc()).limit(limit).offset(offset))
    contacts = result.scalars().all()

    return ContactListResponse(items=contacts, total=total, limit=limit, offset=offset)


@router.get("/contacts/{contact_id}", response_model=ContactDetailResponse)
async def get_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contact).options(selectinload(Contact.events)).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
async def update_contact(contact_id: uuid.UUID, payload: ContactUpdate, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Map 'metadata' field to 'metadata_' attribute
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")

    for field, value in update_data.items():
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    await db.execute(delete(Contact).where(Contact.id == contact_id))
    await db.commit()


@router.post("/contacts/{contact_id}/retry", response_model=ContactResponse)
async def retry_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if contact.status not in RETRYABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot retry contact with status '{contact.status.value}'. "
            f"Retryable statuses: {', '.join(s.value for s in RETRYABLE_STATUSES)}",
        )

    contact.status = ContactStatus.pending
    contact.current_cadence_step = 0
    await db.commit()
    await db.refresh(contact)
    return contact
