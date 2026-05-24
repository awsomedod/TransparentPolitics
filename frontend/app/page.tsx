"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchPoliticians, PoliticianSummary } from "@/lib/api";

function partyColor(party: string | null): string {
  switch (party) {
    case "Democratic":
      return "bg-blue-100 text-blue-800";
    case "Republican":
      return "bg-red-100 text-red-800";
    case "Independent":
      return "bg-purple-100 text-purple-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
}

function PoliticianCard({ p }: { p: PoliticianSummary }) {
  return (
    <Link
      href={`/politicians/${p.bioguide_id}`}
      className="flex items-center justify-between rounded-lg border bg-white px-4 py-3 transition hover:shadow-md"
    >
      <div>
        <p className="font-medium text-gray-900">{p.display_name}</p>
        <p className="text-sm text-gray-500">
          {p.office_title} — {p.state}
        </p>
      </div>
      <span
        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${partyColor(p.party)}`}
      >
        {p.party ?? "Unknown"}
      </span>
    </Link>
  );
}

export default function Home() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [partyFilter, setPartyFilter] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const pageSize = 20;

  const { data, isLoading, error } = useQuery({
    queryKey: ["politicians", page, partyFilter, stateFilter],
    queryFn: () =>
      fetchPoliticians({
        page,
        page_size: pageSize,
        party: partyFilter || undefined,
        state: stateFilter || undefined,
      }),
  });

  const filtered = data?.items.filter((p) =>
    search
      ? p.display_name.toLowerCase().includes(search.toLowerCase())
      : true
  );

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">
          Members of Congress
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {data?.total ?? "..."} current members — sourced from Congress.gov API
        </p>
      </div>

      <div className="mb-4 flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search by name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={partyFilter}
          onChange={(e) => {
            setPartyFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-md border px-3 py-2 text-sm"
        >
          <option value="">All parties</option>
          <option value="Democratic">Democratic</option>
          <option value="Republican">Republican</option>
          <option value="Independent">Independent</option>
        </select>
        <input
          type="text"
          placeholder="Filter by state..."
          value={stateFilter}
          onChange={(e) => {
            setStateFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {isLoading && <p className="text-gray-500">Loading...</p>}
      {error && (
        <p className="text-red-600">
          Error loading data. Is the backend running?
        </p>
      )}

      <div className="grid gap-2">
        {filtered?.map((p) => (
          <PoliticianCard key={p.bioguide_id} p={p} />
        ))}
      </div>

      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="rounded border px-3 py-1 text-sm disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-sm text-gray-600">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="rounded border px-3 py-1 text-sm disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
