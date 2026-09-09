import type { Coverage } from "../types";
import { EvidenceBadge, Meter, SectionTitle } from "../components/ui";

export default function PoolGaps({
  coverage,
  gaps,
}: {
  coverage: Coverage[];
  gaps: Coverage[];
}) {
  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow">Pool analysis</p>
        <h1 className="mt-1 text-3xl font-semibold text-white">Talent-pool gaps</h1>
        <p className="mt-2 max-w-3xl text-sm text-soft">
          A criterion nobody meets is a finding about the requisition and the
          market — not a failing of any individual candidate. It is reported once,
          here, rather than repeated as twelve separate rejections.
        </p>
      </div>

      {gaps.length === 0 ? (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-4 text-sm text-emerald-200">
          Every requirement is demonstrated by at least one candidate.
        </div>
      ) : (
        <div className="space-y-4">
          {gaps.map((gap) => (
            <div
              key={gap.requirementId}
              className="rounded-lg border border-rose-500/40 bg-rose-500/5 p-5"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <div>
                  <p className="eyebrow text-rose-300">Pool gap detected</p>
                  <h3 className="mt-1 text-xl font-semibold text-white">
                    {gap.skill}
                  </h3>
                </div>
                <p className="font-mono text-2xl text-rose-300">
                  {gap.satisfiedCount} / {gap.totalCandidates}
                </p>
              </div>

              <p className="mt-3 text-sm text-slate-200">{gap.conclusion}</p>

              <div className="mt-4">
                <p className="eyebrow mb-2">Closest evidence in the pool</p>
                {gap.nearMisses.length === 0 ? (
                  <p className="text-sm text-soft">
                    No candidate offered anything toward this criterion.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {gap.nearMisses.map((miss) => (
                      <div
                        key={miss.applicationId}
                        className="flex flex-wrap items-start gap-3 rounded bg-black/20 px-3 py-2"
                      >
                        <span className="font-mono text-xs text-white">
                          {miss.applicationId}
                        </span>
                        <EvidenceBadge level={miss.evidenceLevel} />
                        <span className="text-sm text-slate-300">{miss.note}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div>
        <SectionTitle>Coverage across every criterion</SectionTitle>
        <div className="card space-y-3">
          {coverage.map((entry) => (
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
                  <span className="ml-2 font-mono text-[10px] text-soft">
                    {entry.necessity}
                  </span>
                </span>
                <span
                  className={`font-mono text-xs ${
                    entry.isGap ? "text-rose-400" : "text-soft"
                  }`}
                >
                  {entry.satisfiedCount}/{entry.totalCandidates}
                </span>
              </div>
              <Meter value={entry.coverageRatio} danger={entry.isGap} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
