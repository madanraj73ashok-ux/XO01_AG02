// Thin fetch wrapper over the FastAPI engine layer.
// Every screen renders real engine output - there is no mock data path.

import type {
  CandidateDetail,
  CandidateSummary,
  Comparison,
  Coverage,
  Dashboard,
  Requisition,
  ShortlistEntry,
} from "./types";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} on ${path}`);
  }
  return (await response.json()) as T;
}

export const api = {
  dashboard: () => get<Dashboard>("/api/dashboard"),
  requisition: () => get<Requisition>("/api/requisition"),
  candidates: () => get<CandidateSummary[]>("/api/candidates"),
  candidate: (id: string) => get<CandidateDetail>(`/api/candidates/${id}`),
  shortlist: () => get<ShortlistEntry[]>("/api/shortlist"),
  pool: () => get<{ coverage: Coverage[]; gaps: Coverage[] }>("/api/pool"),
  compare: (left: string, right: string) =>
    get<Comparison>(`/api/compare?left=${left}&right=${right}`),
};
