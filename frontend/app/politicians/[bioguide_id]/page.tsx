"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { fetchPolitician } from "@/lib/api";

function partyBadge(party: string | null): string {
  switch (party) {
    case "Democratic":
      return "bg-blue-100 text-blue-800 border-blue-200";
    case "Republican":
      return "bg-red-100 text-red-800 border-red-200";
    case "Independent":
      return "bg-purple-100 text-purple-800 border-purple-200";
    default:
      return "bg-gray-100 text-gray-800 border-gray-200";
  }
}

export default function PoliticianPage() {
  const params = useParams();
  const bioguideId = params.bioguide_id as string;

  const { data, isLoading, error } = useQuery({
    queryKey: ["politician", bioguideId],
    queryFn: () => fetchPolitician(bioguideId),
    enabled: !!bioguideId,
  });

  if (isLoading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-600">Politician not found.</p>;
  if (!data) return null;

  const current = data.current_office;

  return (
    <div>
      <Link href="/" className="text-sm text-blue-600 hover:underline">
        &larr; Back to all members
      </Link>

      <div className="mt-4 rounded-lg border bg-white p-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold">{data.display_name}</h1>
            {current && (
              <p className="mt-1 text-gray-600">
                {current.office.title} — {current.jurisdiction?.name}
              </p>
            )}
          </div>
          {current?.party && (
            <span
              className={`rounded-full border px-3 py-1 text-sm font-medium ${partyBadge(current.party.name)}`}
            >
              {current.party.name} ({current.party.short_name})
            </span>
          )}
        </div>

        <div className="mt-6 grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="font-medium text-gray-500">Bioguide ID</span>
            <p>{data.bioguide_id}</p>
          </div>
          <div>
            <span className="font-medium text-gray-500">Birth Year</span>
            <p>{data.birth_date ? data.birth_date.slice(0, 4) : "Unknown"}</p>
          </div>
          {current?.office.chamber && (
            <div>
              <span className="font-medium text-gray-500">Chamber</span>
              <p>{current.office.chamber}</p>
            </div>
          )}
          {current?.start_date && (
            <div>
              <span className="font-medium text-gray-500">Term started</span>
              <p>{current.start_date.slice(0, 4)}</p>
            </div>
          )}
        </div>
      </div>

      {data.terms.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-3 text-lg font-semibold">Terms Served</h2>
          <div className="space-y-2">
            {data.terms.map((term, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded border bg-white px-4 py-3 text-sm"
              >
                <div>
                  <span className="font-medium">{term.office.title}</span>
                  {term.jurisdiction && (
                    <span className="text-gray-500">
                      {" "}
                      — {term.jurisdiction.name}
                    </span>
                  )}
                </div>
                <div className="text-gray-500">
                  {term.start_date?.slice(0, 4) ?? "?"} –{" "}
                  {term.end_date?.slice(0, 4) ?? "present"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="mt-8 text-xs text-gray-400">
        Data provided by the Library of Congress Congress.gov API. All facts
        sourced from official government records.
      </p>
    </div>
  );
}
