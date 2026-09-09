import { useEffect, useState } from "react";
import type { ReactNode } from "react";
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

export default function App() {
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

  function open(id: string) {
    setSelected(id);
    setTab("candidates");
  }

  function changeTab(next: Tab) {
    setTab(next);
    setSelected(null);
  }

  if (error) {
    return (
      <Shell tab={tab} onTab={changeTab}>
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-6">
          <p className="font-semibold text-rose-200">Cannot reach the engine.</p>
          <p className="mt-2 font-mono text-xs text-rose-300">{error}</p>
          <p className="mt-4 text-sm text-slate-300">
            Start the backend with{" "}
            <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-xs">
              uvicorn api:app --port 8000
            </code>{" "}
            from the <span className="font-mono">evidencehire/</span> directory.
          </p>
        </div>
      </Shell>
    );
  }

  const loading = !dashboard || !requisition || !pool;

  return (
    <Shell tab={tab} onTab={changeTab}>
      {loading ? (
        <p className="text-sm text-soft">Loading engine output…</p>
      ) : tab === "dashboard" ? (
        <Dashboard data={dashboard} />
      ) : tab === "requisition" ? (
        <RequisitionView data={requisition} />
      ) : tab === "candidates" ? (
        selected && detail ? (
          <CandidateDetailScreen data={detail} onBack={() => setSelected(null)} />
        ) : (
          <CandidateList candidates={candidates} onOpen={open} />
        )
      ) : tab === "compare" ? (
        <Compare candidates={candidates} />
      ) : (
        <PoolGaps coverage={pool.coverage} gaps={pool.gaps} />
      )}
    </Shell>
  );
}

function Shell({
  tab,
  onTab,
  children,
}: {
  tab: Tab;
  onTab: (tab: Tab) => void;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      <aside className="w-60 shrink-0 border-r border-white/10 bg-ink/60 p-6">
        <h1 className="text-lg font-semibold text-white">EvidenceHire</h1>
        <p className="mt-2 text-xs leading-relaxed text-soft">
          Don&rsquo;t just read what candidates claim. Verify what the evidence
          supports.
        </p>

        <nav className="mt-8 space-y-1">
          {TABS.map((entry) => (
            <button
              key={entry.key}
              onClick={() => onTab(entry.key)}
              className={`block w-full rounded px-3 py-2 text-left text-sm transition ${
                tab === entry.key
                  ? "bg-accent/15 font-medium text-accent"
                  : "text-slate-300 hover:bg-white/5"
              }`}
            >
              {entry.label}
            </button>
          ))}
        </nav>

        <p className="mt-10 font-mono text-[10px] leading-relaxed text-soft">
          PS02 · X&rsquo;O Code 2026
          <br />
          Team BOT BABY
        </p>
      </aside>

      <main className="flex-1 overflow-x-hidden px-10 py-8">{children}</main>
    </div>
  );
}
