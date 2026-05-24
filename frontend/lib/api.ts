export interface PoliticianSummary {
  bioguide_id: string;
  display_name: string;
  party: string | null;
  state: string | null;
  office_title: string | null;
  is_current: boolean;
}

export interface PaginatedResponse {
  items: PoliticianSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface OfficeDetail {
  title: string;
  level: string;
  chamber: string | null;
}

export interface PartyDetail {
  name: string;
  short_name: string;
}

export interface JurisdictionDetail {
  name: string;
  type: string;
}

export interface OfficeholderDetail {
  office: OfficeDetail;
  party: PartyDetail | null;
  jurisdiction: JurisdictionDetail | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
}

export interface PoliticianDetail {
  bioguide_id: string;
  canonical_name: string;
  display_name: string;
  birth_date: string | null;
  death_date: string | null;
  current_office: OfficeholderDetail | null;
  terms: OfficeholderDetail[];
}

const API_BASE = "/api/v1";

export async function fetchPoliticians(params: {
  page?: number;
  page_size?: number;
  party?: string;
  state?: string;
}): Promise<PaginatedResponse> {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set("page", String(params.page));
  if (params.page_size) searchParams.set("page_size", String(params.page_size));
  if (params.party) searchParams.set("party", params.party);
  if (params.state) searchParams.set("state", params.state);

  const res = await fetch(`${API_BASE}/politicians?${searchParams}`);
  if (!res.ok) throw new Error("Failed to fetch politicians");
  return res.json();
}

export async function fetchPolitician(
  bioguideId: string
): Promise<PoliticianDetail> {
  const res = await fetch(`${API_BASE}/politicians/${bioguideId}`);
  if (!res.ok) throw new Error("Failed to fetch politician");
  return res.json();
}
