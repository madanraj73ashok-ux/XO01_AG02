// The original recruiter console over the fixed 12-candidate demo pool.
//
// Kept intact and reachable at /console. It runs against the offline demo
// dataset rather than the live product store, which is exactly what makes it
// useful: the build plan asks for a deterministic demo that still works when
// no external service is available.

import { useEffect, useState } from "react";
import { api } from "./api";
import type {
  CandidateDetail as Detail,
  CandidateSummary,
  Coverage,
  Dashboard as DashboardData,
  Requisition,
} from "./types";
import Dashboard from "./screens/Dashboard";
import RequisitionView from "./screens/RequisitionView";
import CandidateList from "./screens/CandidateList";
import CandidateDetailScreen from "./screens/CandidateDetail";
import PoolGaps from "./screens/PoolGaps";
import Compare from "./screens/Compare";

type Tab = "dashboard" | "requisition" | "candidates" | "compare" | "pool";

const TABS: { key: Tab; label: string }[] = [
  { key: "dashboard", label: "Dashboard" },
  { key: "requisition", label: "Requisition" },
  { key: "candidates", label: "Candidates" },
  { key: "compare", label: "Comparison" },
  { key: "pool", label: "Pool gaps" },
];

export default function LegacyConsole() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [selected, setSelected] = useState<string | null>(null);

  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [requisition, setRequisition] = useState<Requisition | null>(null);
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [pool, setPool] = useState<{ coverage: Coverage[]; gaps: Coverage[] } | null>(
    null
  );
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.dashboard(), api.requisition(), api.candidates(), api.pool()])
      .then(([d, r, c, p]) => {
        setDashboard(d);
        setRequisition(r);
        setCandidates(c);
        setPool(p);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    api
      .candidate(selected)
      .then(setDetail)
      .catch((e: Error) => setError(e.message));
  }, [selected]);

  if (error) {
    return (
      <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-6">
        <p className="font-semibold text-rose-200">Cannot reach the engine.</p>
        <p className="mt-2 font-mono text-xs text-rose-300">{error}</p>
      </div>
    );
  }

  const loading = !dashboard || !requisition || !pool;

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-semibold text-white">Offline demo pool</h2>
        <p className="mt-1 text-sm text-soft">
          The original 12-candidate evaluation set, assessed by the same engine.
          No network or external service is involved.
        </p>
      </header>

      <nav className="flex flex-wrap gap-1">
        {TABS.map((entry) => (
          <button
            key={entry.key}
            onClick={() => {
              setTab(entry.key);
              setSelected(null);
            }}
            className={`rounded px-3 py-1.5 text-sm transition ${
              tab === entry.key
                ? "bg-accent/15 font-medium text-accent"
                : "text-slate-300 hover:bg-white/5"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </nav>

      {loading ? (
        <p className="text-sm text-soft">Loading engine output...</p>
      ) : tab === "dashboard" ? (
        <Dashboard data={dashboard} />
      ) : tab === "requisition" ? (
        <RequisitionView data={requisition} />
      ) : tab === "candidates" ? (
        selected && detail ? (
          <CandidateDetailScreen data={detail} onBack={() => setSelected(null)} />
        ) : (
          <CandidateList
            candidates={candidates}
            onOpen={(id) => {
              setSelected(id);
              setTab("candidates");
            }}
          />
        )
      ) : tab === "compare" ? (
        <Compare candidates={candidates} />
      ) : (
        <PoolGaps coverage={pool.coverage} gaps={pool.gaps} />
      )}
    </div>
  );
}
