"""
Congress members ETL asset.

Pipeline: Congress.gov API → MinIO snapshot → normalize → upsert DB

This module is built incrementally. Current state: normalization helpers only.
The Dagster @asset function and DB upsert logic will be added in subsequent steps.
"""

# ---------------------------------------------------------------------------
# Normalization helpers
# Pure functions — no I/O, no side effects.
# Applied inline when processing each member record during the asset run.
# ---------------------------------------------------------------------------

# Congress.gov /v3/member (list endpoint) returns partyName as the verbose form
# e.g. "Democratic". The detail endpoint's partyHistory uses the same convention.
# We map all known variants to the canonical short form stored in the parties table.
# Unknown values pass through unchanged so novel parties are preserved rather than
# silently dropped.
_PARTY_ALIASES: dict[str, str] = {
    "Democratic": "Democrat",
    "Democrat": "Democrat",
    "Democratic-Farmer-Labor": "Democrat",  # Minnesota DFL — nationally affiliated with Democrats
    "Republican": "Republican",
    "Independent": "Independent",
    "Libertarian": "Libertarian",
    "Green": "Green",
}


def normalize_party(raw: str | None) -> str:
    """
    Map a raw partyName string from Congress.gov to the canonical form
    stored in the parties table.

    Returns the input unchanged if it is not in the known-aliases map, so
    novel or unusual parties are preserved rather than silently discarded.
    Returns "Unknown" only when the input is None (the API omitted the field).
    """
    if raw is None:
        return "Unknown"
    return _PARTY_ALIASES.get(raw, raw)


# All 50 states + DC + US territories with a congressional delegation.
# Used as a fallback when stateCode is absent from the API response.
# In practice, MemberDetail.current_term.state_code already carries the
# 2-letter code, so this map is hit only in unexpected edge cases.
_STATE_NAME_TO_CODE: dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT",
    "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
    "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO",
    "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND",
    "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT",
    "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
    # DC and territories that hold congressional seats
    "District of Columbia": "DC",
    "Puerto Rico": "PR",
    "Guam": "GU",
    "Virgin Islands": "VI",
    "American Samoa": "AS",
    "Northern Mariana Islands": "MP",
}


def normalize_state_code(
    state_code: str | None,
    state_name: str | None = None,
) -> str | None:
    """
    Return a 2-letter state / territory code.

    Prefers state_code (already 2-letter from MemberDetail.current_term.state_code).
    Falls back to looking up state_name in the full-name map.
    Returns None only if both inputs are absent or unrecognised.
    """
    if state_code:
        return state_code.upper()
    if state_name:
        return _STATE_NAME_TO_CODE.get(state_name)
    return None


# Congress.gov memberType strings → canonical office title stored in offices table.
# memberType is the most precise source; chamber is the fallback.
_MEMBER_TYPE_TO_OFFICE: dict[str, str] = {
    "Senator": "US Senator",
    "Representative": "US Representative",
    "Resident Commissioner": "US Resident Commissioner",  # Puerto Rico's non-voting delegate
    "Delegate": "US Delegate",                             # DC, Guam, Virgin Islands, etc.
}

_CHAMBER_TO_OFFICE: dict[str, str] = {
    "Senate": "US Senator",
    "House of Representatives": "US Representative",
}


def normalize_office_title(
    member_type: str | None,
    chamber: str | None = None,
) -> str | None:
    """
    Return the canonical office title for an officeholders row.

    Prefers memberType from the term record (more specific).
    Falls back to chamber string if memberType is absent or unrecognised.
    Returns None if neither maps to a known title, so the caller can decide
    whether to skip or log the record.
    """
    if member_type and member_type in _MEMBER_TYPE_TO_OFFICE:
        return _MEMBER_TYPE_TO_OFFICE[member_type]
    if chamber and chamber in _CHAMBER_TO_OFFICE:
        return _CHAMBER_TO_OFFICE[chamber]
    return None
