// Shared presentational pieces. Deliberately small and unopinionated so the
// screens stay readable and the vocabulary (status colours, evidence levels)
// stays consistent everywhere it appears.

import type { ReactNode } from "react";

export const STATUS_STYLE: Record<string, string> = {
  strong: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30",
  moderate: "bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/30",
  weak: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30",
  unaddressed: "bg-rose-500/15 text-rose-300 ring-1 ring-rose-500/30",
};

export const EVIDENCE_STYLE: Record<string, string> = {
  E0: "bg-rose-500/20 text-rose-200",
  E1: "bg-amber-500/20 text-amber-200",
  E2: "bg-sky-500/20 text-sky-200",
  E3: "bg-emerald-500/20 text-emerald-200",
  E4: "bg-emerald-400/25 text-emerald-100",
};

export const STAGES = [
  { key: "applied", label: "Applied" },
  { key: "screening", label: "Screening" },
  { key: "evidence_verification", label: "Evidence Verification" },
  { key: "recruiter_review", label: "Recruiter Review" },
  { key: "shortlisted", label: "Shortlisted" },
  { key: "rejected", label: "Rejected" },
];

export function Badge({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={`pill ${className}`}>{children}</span>;
}

export function StatusBadge({ status, label }: { status: string; label: string }) {
  return <Badge className={STATUS_STYLE[status] ?? ""}>{label}</Badge>;
}

export function EvidenceBadge({ level }: { level: string }) {
  return <Badge className={EVIDENCE_STYLE[level] ?? ""}>{level}</Badge>;
}

export function Stat({
  label,
  value,
  tone = "",
  hint,
}: {
  label: string;
  value: ReactNode;
  tone?: string;
  hint?: string;
}) {
  return (
    <div className="card">
      <p className="eyebrow">{label}</p>
      <p className={`mt-2 text-3xl font-semibold ${tone}`}>{value}</p>
      {hint ? <p className="mt-1 text-xs text-soft">{hint}</p> : null}
    </div>
  );
}

export function SectionTitle({
  children,
  hint,
}: {
  children: ReactNode;
  hint?: string;
}) {
  return (
    <div className="mb-4">
      <h2 className="text-lg font-semibold text-white">{children}</h2>
      {hint ? <p className="mt-1 text-sm text-soft">{hint}</p> : null}
    </div>
  );
}

export function Meter({ value, danger = false }: { value: number; danger?: boolean }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded bg-white/10">
      <div
        className={`h-full rounded ${danger ? "bg-rose-500" : "bg-accent"}`}
        style={{ width: `${Math.max(value * 100, danger ? 2 : 0)}%` }}
      />
    </div>
  );
}

export function Quote({ section, text }: { section: string; text: string }) {
  return (
    <div className="rounded border-l-2 border-accent/60 bg-black/20 px-3 py-2">
      <p className="eyebrow">{section}</p>
      <p className="mt-1 font-mono text-xs leading-relaxed text-slate-200">
        &ldquo;{text}&rdquo;
      </p>
    </div>
  );
}
