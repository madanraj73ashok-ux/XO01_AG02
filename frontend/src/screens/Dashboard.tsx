import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Dashboard as DashboardData } from "../types";
import { Meter, SectionTitle, Stat } from "../components/ui";

const EVIDENCE_FILL: Record<string, string> = {
  E0: "#f43f5e",
  E1: "#f59e0b",
  E2: "#38bdf8",
  E3: "#10b981",
  E4: "#34d399",
};

export default function Dashboard({ data }: { data: DashboardData }) {
  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow">Active requisition</p>
        <h1 className="mt-1 text-3xl font-semibold text-white">
          {data.requisitionTitle}
        </h1>
        <p className="mt-1 text-sm text-soft">{data.requisitionId}</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat label="Applications" value={data.applications} />
        <Stat
          label="Fully qualified"
          value={data.fullyQualified}
          hint="all required criteria demonstrated"
        />
        <Stat
          label="Pool gaps"
          value={data.poolGaps}
          tone="text-rose-400"
          hint={data.gapSkills.join(", ") || "none"}
        />
        <Stat
          label="Unsupported claims"
          value={data.overclaims}
          tone="text-amber-400"
          hint="claimed beyond the evidence"
        />
        <Stat
          label="Contradictions"
          value={data.contradictions}
          tone="text-amber-400"
          hint="within-document conflicts"
        />
      </div>

      {data.requisitionConflicts > 0 && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
          <p className="text-sm text-amber-200">
            <span className="font-semibold">
              {data.requisitionConflicts} requisition issue
              {data.requisitionConflicts > 1 ? "s" : ""} found.
            </span>{" "}
            Surfaced for recruiter review, never resolved automatically — see the
            Requisition tab.
          </p>
        </div>
      )}

      {data.fullyQualified === 0 && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-100">
          {data.fullRequisitionMessage}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card">
          <SectionTitle hint="How well-supported every assessed claim turned out to be.">
            Evidence spread
          </SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.evidenceSpread}>
              <XAxis dataKey="level" stroke="#7a8399" fontSize={12} />
              <YAxis stroke="#7a8399" fontSize={12} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,0.05)" }}
                contentStyle={{
                  background: "#22263a",
                  border: "1px solid rgba(255,255,255,0.15)",
                  borderRadius: 6,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {data.evidenceSpread.map((entry) => (
                  <Cell key={entry.level} fill={EVIDENCE_FILL[entry.level]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <SectionTitle hint="Candidates demonstrating each criterion, out of the whole pool.">
            Requirement coverage
          </SectionTitle>
          <div className="space-y-3">
            {data.coverage.map((entry) => (
              <div key={entry.requirementId}>
                <div className="mb-1 flex items-baseline justify-between text-sm">
                  <span
                    className={
                      entry.necessity === "required"
                        ? "font-medium text-white"
                        : "text-soft"
                    }
                  >
                    {entry.skill}
                  </span>
                  <span
                    className={`font-mono text-xs ${
                      entry.isGap ? "text-rose-400" : "text-soft"
                    }`}
                  >
                    {entry.satisfiedCount}/{entry.totalCandidates}
                    {entry.isGap ? "  GAP" : ""}
                  </span>
                </div>
                <Meter value={entry.coverageRatio} danger={entry.isGap} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
