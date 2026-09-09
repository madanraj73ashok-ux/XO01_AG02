// The parts of the interface that carry the argument.
//
// The evidence ladder, the WHY panel, the terminology verdict and the evidence
// graph are the product. They are grouped here because they must look and read
// the same everywhere they appear - a recruiter and a candidate should see the
// same reasoning about the same claim, not two differently-worded summaries.

import { useState } from "react";
import type { ReactNode } from "react";
import type {
  Conflict,
  ExternalCheck,
  Fit,
  GraphEdge,
  GraphNode,
  Step,
  TerminologyFinding,
  Why,
} from "./api";

export const EVIDENCE_STYLE: Record<string, string> = {
  E0: "bg-rose-500/20 text-rose-200 ring-1 ring-rose-500/40",
  E1: "bg-amber-500/20 text-amber-200 ring-1 ring-amber-500/40",
  E2: "bg-sky-500/20 text-sky-200 ring-1 ring-sky-500/40",
  E3: "bg-emerald-500/20 text-emerald-200 ring-1 ring-emerald-500/40",
  E4: "bg-emerald-400/30 text-emerald-100 ring-1 ring-emerald-400/50",
};

export const RELATIONSHIP_STYLE: Record<string, string> = {
  EXACT: "bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/30",
  EQUIVALENT: "bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/30",
  RELATED: "bg-amber-500/15 text-amber-200 ring-1 ring-amber-500/30",
  NOT_EQUIVALENT: "bg-rose-500/15 text-rose-200 ring-1 ring-rose-500/30",
  UNKNOWN: "bg-white/10 text-slate-300 ring-1 ring-white/15",
};

const STATE_STYLE: Record<string, string> = {
  public: "bg-emerald-500/15 text-emerald-200",
  private_auth_required: "bg-amber-500/15 text-amber-200",
  not_found: "bg-rose-500/15 text-rose-200",
  unable_to_verify: "bg-white/10 text-slate-300",
};

export function Pill({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${className}`}
    >
      {children}
    </span>
  );
}

export function EvidenceBadge({ level }: { level: string }) {
  return <Pill className={EVIDENCE_STYLE[level] ?? ""}>{level}</Pill>;
}

export function Panel({
  title,
  hint,
  children,
  tone = "",
}: {
  title?: string;
  hint?: string;
  children: ReactNode;
  tone?: string;
}) {
  return (
    <section className={`rounded-xl border border-white/10 bg-panel/50 p-5 ${tone}`}>
      {title ? (
        <header className="mb-3">
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          {hint ? <p className="mt-1 text-xs text-soft">{hint}</p> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function LevelBanner({
  level,
  label,
  supported,
  total,
}: {
  level: number;
  label: string;
  supported: number;
  total: number;
}) {
  const tone =
    level >= 4
      ? "from-emerald-500/25"
      : level === 3
        ? "from-sky-500/25"
        : level === 2
          ? "from-amber-500/25"
          : "from-rose-500/25";

  return (
    <div
      className={`rounded-xl border border-white/10 bg-gradient-to-r ${tone} to-transparent p-6`}
    >
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-soft">
        Evidence-based result
      </p>
      <p className="mt-2 text-3xl font-semibold text-white">
        Level {level} &mdash; {label}
      </p>
      <p className="mt-2 text-sm text-slate-300">
        {supported} of {total} required criteria supported by evidence.
      </p>
      <p className="mt-3 max-w-2xl text-xs leading-relaxed text-soft">
        A level is a band derived from the requirement matrix below, not a
        score. The matrix is the explanation; this is only its headline.
      </p>
    </div>
  );
}

/** The requisition conflict, stated and left for a human. */
export function ConflictNotice({ conflicts }: { conflicts: Conflict[] }) {
  if (!conflicts.length) return null;
  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-5">
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-amber-200">
        Requisition conflict
      </p>
      {conflicts.map((conflict) => (
        <div key={conflict.requirementIds.join("-") + conflict.kind} className="mt-3">
          <p className="text-sm text-amber-100">{conflict.detail}</p>
          <p className="mt-1 text-xs text-amber-200/80">{conflict.recommendation}</p>
        </div>
      ))}
      <p className="mt-4 font-mono text-[11px] uppercase tracking-wider text-amber-200">
        Status: recruiter review required
      </p>
    </div>
  );
}

export function TerminologyBadge({ finding }: { finding: TerminologyFinding | null }) {
  if (!finding) return null;
  return (
    <Pill className={RELATIONSHIP_STYLE[finding.relationship] ?? ""}>
      {finding.relationship.replace("_", " ")}
    </Pill>
  );
}

/** The WHY panel. The unsupported branch is the one that matters. */
export function WhyPanel({ why, skill }: { why: Why; skill: string }) {
  const unsupported = why.evidence_level === "E0";

  return (
    <div className="mt-3 rounded-lg border border-white/10 bg-black/25 p-4">
      <div className="flex items-center gap-2">
        <EvidenceBadge level={why.evidence_level} />
        <p className="text-sm font-medium text-white">{why.verdict}</p>
      </div>

      {why.reasons.length ? (
        <ul className="mt-3 space-y-1">
          {why.reasons.map((reason) => (
            <li key={reason} className="flex gap-2 text-xs text-slate-300">
              <span className="text-accent">&bull;</span>
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {why.quotes.length ? (
        <div className="mt-3 space-y-2">
          <p className="eyebrow">Evidence quoted from the application</p>
          {why.quotes.map((quote, index) => (
            <blockquote
              key={`${quote.section}-${index}`}
              className="rounded border-l-2 border-accent/60 bg-black/30 px-3 py-2"
            >
              <p className="font-mono text-[10px] uppercase tracking-wider text-soft">
                {quote.section} &middot; {quote.note}
              </p>
              <p className="mt-1 font-mono text-xs leading-relaxed text-slate-200">
                &ldquo;{quote.text}&rdquo;
              </p>
            </blockquote>
          ))}
        </div>
      ) : null}

      {unsupported ? (
        <div className="mt-3 space-y-2">
          <p className="eyebrow">Evidence searched</p>
          <p className="text-xs text-slate-300">{why.searched.join(", ")}</p>
          <p className="text-xs text-slate-300">
            Supporting evidence for {skill}: <strong>none found</strong>.
          </p>
        </div>
      ) : null}

      {why.caveat ? (
        <p className="mt-3 rounded bg-white/5 px-3 py-2 text-xs italic leading-relaxed text-soft">
          {why.caveat}
        </p>
      ) : null}
    </div>
  );
}

/** One requirement row, expandable into its WHY. */
export function RequirementRow({ fit }: { fit: Fit }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-white/5 py-3 last:border-0">
      <div className="flex flex-wrap items-center gap-3">
        <EvidenceBadge level={fit.evidenceLevel} />
        <span className="min-w-[10rem] text-sm font-medium text-white">{fit.skill}</span>
        <Pill
          className={
            fit.necessity === "required"
              ? "bg-white/10 text-slate-300"
              : "bg-white/5 text-soft"
          }
        >
          {fit.necessity}
        </Pill>
        <span className="text-xs text-soft">{fit.statusLabel}</span>
        <TerminologyBadge finding={fit.terminology} />
        {fit.isOverclaimed ? (
          <Pill className="bg-rose-500/20 text-rose-200">unsupported claim</Pill>
        ) : null}
        <button
          onClick={() => setOpen(!open)}
          className="ml-auto rounded border border-accent/40 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent transition hover:bg-accent/10"
        >
          {open ? "hide" : "why?"}
        </button>
      </div>

      {open ? (
        <>
          <WhyPanel why={fit.why} skill={fit.skill} />
          <div className="mt-2 rounded bg-black/20 px-3 py-2">
            <p className="eyebrow">How the confidence was reached</p>
            <ul className="mt-1 space-y-0.5">
              {fit.confidenceFactors.map((factor) => (
                <li key={factor.reason} className="font-mono text-[11px] text-slate-300">
                  {factor.delta >= 0 ? "+" : ""}
                  {factor.delta.toFixed(2)} &nbsp;{factor.reason}
                </li>
              ))}
              <li className="font-mono text-[11px] text-white">
                = {fit.confidence.toFixed(2)} confidence
              </li>
            </ul>
          </div>
        </>
      ) : null}
    </div>
  );
}

/** The live investigation timeline. Renders backend state and nothing else. */
export function Timeline({ steps }: { steps: Step[] }) {
  const mark: Record<string, string> = {
    done: "✓",
    active: "●",
    failed: "✕",
    skipped: "–",
    pending: "○",
  };
  const tone: Record<string, string> = {
    done: "text-emerald-300",
    active: "text-accent",
    failed: "text-rose-300",
    skipped: "text-soft",
    pending: "text-slate-600",
  };

  return (
    <ol className="space-y-2">
      {steps.map((step) => (
        <li key={step.key} className="flex gap-3">
          <span
            className={`mt-0.5 w-4 font-mono text-sm ${tone[step.state]} ${
              step.state === "active" ? "animate-pulse" : ""
            }`}
          >
            {mark[step.state]}
          </span>
          <div className="min-w-0 flex-1">
            <p
              className={`text-sm ${
                step.state === "pending" ? "text-slate-500" : "text-slate-100"
              }`}
            >
              {step.label}
            </p>
            {step.detail ? (
              <p className="mt-0.5 break-words font-mono text-[11px] leading-relaxed text-soft">
                {step.detail}
              </p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function ExternalEvidence({ checks }: { checks: ExternalCheck[] }) {
  if (!checks.length) {
    return (
      <p className="text-xs text-soft">
        No public links were supplied with this application, so no external
        source was checked. That is an absence of input, not a finding.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {checks.map((check) => (
        <div key={check.target} className="rounded-lg bg-black/25 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Pill className={STATE_STYLE[check.state] ?? ""}>
              {check.state.replace(/_/g, " ")}
            </Pill>
            <span className="font-mono text-xs text-white">{check.target}</span>
            <span className="text-[11px] text-soft">{check.kindLabel}</span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-300">{check.note}</p>
          {check.contentHash ? (
            <p className="mt-1 break-all font-mono text-[10px] text-soft">
              sha256 {check.contentHash}
            </p>
          ) : null}
          {!check.canCorroborate ? (
            <p className="mt-1 text-[11px] italic text-soft">
              This result adds no support and reduces nothing.
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

/** The evidence graph: candidate to claims to requirements, drawn from real data. */
export function EvidenceGraph({
  nodes,
  edges,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
}) {
  const [selected, setSelected] = useState<GraphNode | null>(null);

  const columns: Record<string, GraphNode[]> = {
    candidate: nodes.filter((node) => node.kind === "candidate"),
    evidence: nodes.filter((node) => node.kind === "evidence"),
    claim: nodes.filter((node) => node.kind === "claim"),
    requirement: nodes.filter((node) => node.kind === "requirement"),
  };

  const width = 900;
  const rowHeight = 34;
  const height =
    Math.max(
      columns.evidence.length,
      columns.claim.length,
      columns.requirement.length,
      3
    ) *
      rowHeight +
    60;

  const x: Record<string, number> = {
    candidate: 70,
    evidence: 280,
    claim: 520,
    requirement: 760,
  };

  const position = new Map<string, { x: number; y: number }>();
  (Object.keys(columns) as (keyof typeof columns)[]).forEach((kind) => {
    const list = columns[kind];
    const span = height - 50;
    list.forEach((node, index) => {
      const y = 30 + (span * (index + 0.5)) / Math.max(list.length, 1);
      position.set(node.id, { x: x[kind], y });
    });
  });

  const fill = (node: GraphNode) => {
    if (node.kind === "candidate") return "#eb6c36";
    if (node.kind === "requirement") {
      const level = node.evidenceLevel ?? "E0";
      if (level === "E0") return "#f43f5e";
      if (level === "E1") return "#f59e0b";
      if (level === "E2") return "#38bdf8";
      return "#34d399";
    }
    if (node.kind === "claim") return "#a78bfa";
    return "#64748b";
  };

  return (
    <div>
      <div className="overflow-x-auto rounded-lg bg-black/30 p-2">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full min-w-[720px]">
          {edges.map((edge, index) => {
            const from = position.get(edge.source);
            const to = position.get(edge.target);
            if (!from || !to) return null;
            const dash = edge.kind === "RELATED_TO" ? "4 3" : undefined;
            const stroke =
              edge.kind === "RELATED_TO"
                ? "#f59e0b"
                : edge.kind === "EQUIVALENT_TO"
                  ? "#34d399"
                  : "#475569";
            return (
              <path
                key={`${edge.source}-${edge.target}-${index}`}
                d={`M ${from.x} ${from.y} C ${(from.x + to.x) / 2} ${from.y}, ${
                  (from.x + to.x) / 2
                } ${to.y}, ${to.x} ${to.y}`}
                fill="none"
                stroke={stroke}
                strokeWidth={1.2}
                strokeDasharray={dash}
                opacity={0.7}
              />
            );
          })}

          {nodes.map((node) => {
            const point = position.get(node.id);
            if (!point) return null;
            return (
              <g
                key={node.id}
                transform={`translate(${point.x}, ${point.y})`}
                onClick={() => setSelected(node)}
                className="cursor-pointer"
              >
                <circle r={node.kind === "candidate" ? 9 : 6} fill={fill(node)} />
                <text
                  x={12}
                  y={4}
                  fontSize={11}
                  fill="#cbd5f5"
                  fontFamily="ui-monospace, monospace"
                >
                  {node.label.length > 26 ? `${node.label.slice(0, 26)}...` : node.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mt-3 flex flex-wrap gap-4 font-mono text-[10px] uppercase tracking-wider text-soft">
        <span>
          <span className="mr-1 text-accent">&#9679;</span>candidate
        </span>
        <span>
          <span className="mr-1 text-slate-400">&#9679;</span>evidence
        </span>
        <span>
          <span className="mr-1 text-violet-400">&#9679;</span>claim
        </span>
        <span>
          <span className="mr-1 text-emerald-400">&#9679;</span>requirement
        </span>
        <span className="text-amber-300">dashed = related, not equivalent</span>
      </div>

      {selected ? (
        <div className="mt-3 rounded-lg bg-black/30 p-3">
          <p className="eyebrow">{selected.kind}</p>
          <p className="mt-1 text-sm text-white">{selected.label}</p>
          {selected.text ? (
            <p className="mt-1 font-mono text-xs leading-relaxed text-slate-300">
              &ldquo;{selected.text}&rdquo;
            </p>
          ) : null}
          {selected.evidenceLevel ? (
            <p className="mt-2">
              <EvidenceBadge level={selected.evidenceLevel} />
            </p>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 text-xs text-soft">Select a node to see what backs it.</p>
      )}
    </div>
  );
}
