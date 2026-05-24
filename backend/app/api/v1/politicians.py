"""Politicians API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.schemas import (
    OfficeholderSchema,
    PaginatedResponse,
    PoliticianDetail,
    PoliticianSummary,
)
from app.db.models.person import Officeholder, Person
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/politicians", tags=["politicians"])


@router.get("", response_model=PaginatedResponse)
async def list_politicians(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=250, description="Items per page"),
    party: str | None = Query(None, description="Filter by party name"),
    state: str | None = Query(None, description="Filter by state name"),
    current_only: bool = Query(True, description="Only current officeholders"),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse:
    """List politicians with pagination and optional filters."""

    # Base query joining officeholders for filtering
    query = (
        select(Person)
        .join(Officeholder, Officeholder.person_id == Person.id)
        .options(
            selectinload(Person.officeholders).joinedload(Officeholder.office),
            selectinload(Person.officeholders).joinedload(Officeholder.party),
            selectinload(Person.officeholders).joinedload(Officeholder.jurisdiction),
        )
    )

    if current_only:
        query = query.where(Officeholder.is_current.is_(True))

    if party:
        from app.db.models.reference import Party
        query = query.join(
            Party, Officeholder.party_id == Party.id
        ).where(Party.name.ilike(f"%{party}%"))

    if state:
        from app.db.models.reference import Jurisdiction
        query = query.join(
            Jurisdiction, Officeholder.jurisdiction_id == Jurisdiction.id
        ).where(Jurisdiction.name.ilike(f"%{state}%"))

    query = query.distinct()

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(Person.canonical_name).offset(offset).limit(page_size)
    result = await session.execute(query)
    persons = result.scalars().unique().all()

    # Build response
    items = []
    for person in persons:
        current_oh = next(
            (oh for oh in person.officeholders if oh.is_current), None
        )
        items.append(PoliticianSummary(
            bioguide_id=person.bioguide_id or "",
            display_name=person.display_name,
            party=current_oh.party.name if current_oh and current_oh.party else None,
            state=(
                current_oh.jurisdiction.name
                if current_oh and current_oh.jurisdiction
                else None
            ),
            office_title=(
                current_oh.office.title if current_oh else None
            ),
            is_current=current_oh is not None,
        ))

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{bioguide_id}", response_model=PoliticianDetail)
async def get_politician(
    bioguide_id: str,
    session: AsyncSession = Depends(get_session),
) -> PoliticianDetail:
    """Get full detail for a single politician by bioguide_id."""

    query = (
        select(Person)
        .where(Person.bioguide_id == bioguide_id)
        .options(
            selectinload(Person.officeholders).joinedload(Officeholder.office),
            selectinload(Person.officeholders).joinedload(Officeholder.party),
            selectinload(Person.officeholders).joinedload(Officeholder.jurisdiction),
        )
    )
    result = await session.execute(query)
    person = result.scalars().first()

    if not person:
        raise HTTPException(status_code=404, detail="Politician not found")

    current_oh = next(
        (oh for oh in person.officeholders if oh.is_current), None
    )

    terms = [
        OfficeholderSchema.model_validate(oh)
        for oh in sorted(
            person.officeholders,
            key=lambda oh: oh.start_date or "",
            reverse=True,
        )
    ]

    return PoliticianDetail(
        bioguide_id=person.bioguide_id or "",
        canonical_name=person.canonical_name,
        display_name=person.display_name,
        birth_date=person.birth_date,
        death_date=person.death_date,
        current_office=(
            OfficeholderSchema.model_validate(current_oh) if current_oh else None
        ),
        terms=terms,
    )
