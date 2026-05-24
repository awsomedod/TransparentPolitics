"""Response schemas for the politicians endpoints."""

from datetime import date

from pydantic import BaseModel


class PartySchema(BaseModel):
    name: str
    short_name: str

    class Config:
        from_attributes = True


class JurisdictionSchema(BaseModel):
    name: str
    type: str

    class Config:
        from_attributes = True


class OfficeSchema(BaseModel):
    title: str
    level: str
    chamber: str | None = None

    class Config:
        from_attributes = True


class OfficeholderSchema(BaseModel):
    office: OfficeSchema
    party: PartySchema | None = None
    jurisdiction: JurisdictionSchema | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool

    class Config:
        from_attributes = True


class PoliticianSummary(BaseModel):
    """Returned in the list endpoint."""

    bioguide_id: str
    display_name: str
    party: str | None = None
    state: str | None = None
    office_title: str | None = None
    is_current: bool = False

    class Config:
        from_attributes = True


class PoliticianDetail(BaseModel):
    """Returned in the detail endpoint."""

    bioguide_id: str
    canonical_name: str
    display_name: str
    birth_date: date | None = None
    death_date: date | None = None
    current_office: OfficeholderSchema | None = None
    terms: list[OfficeholderSchema] = []

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    """Wrapper for paginated list responses."""

    items: list[PoliticianSummary]
    total: int
    page: int
    page_size: int
