import type { CandidateSummary } from "../types";
import { Badge, Meter, SectionTitle, STAGES } from "../components/ui";

export default function CandidateList({
  candidates,
  onOpen,
}: {
  candidates: CandidateSummary[];
  onOpen: (id: string) => void;
}) {
  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow">Ranked shortlist</p>
        <h1 className="mt-1 text-3xl font-semibold text-white">Candidates</h1>
        <p className="mt-2 max-w-3xl text-sm text-soft">
          Ordered by required-criteria coverage, then evidence depth. The order is
          a reading sequence, not a rating — adjacent candidates usually differ in
          kind rather than in quality.
        </p>
      </div>

      <Pipeline candidates={candidates} />

      <div className="space-y-3">
        {candidates.map((candidate) => (
          <button
            key={candidate.applicationId}
            onClick={() => onOpen(candidate.applicationId)}
            className="card w-full text-left transition hover:border-accent/50 hover:bg-panel"
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono text-xs text-soft">
                    #{candidate.rank}
                  </span>
                  <span className="font-semibold text-white">
                    {candidate.applicationId}
                  </span>
                  <span className="text-sm text-slate-300">
                    {candidate.candidateName}
                  </span>
                  {candidate.overclaims > 0 && (
                    <Badge className="bg-amber-500/20 text-amber-200">
                      {candidate.overclaims} unsupported
                    </Badge>
                  )}
                  {candidate.contradictions > 0 && (
                    <Badge className="bg-rose-500/20 text-rose-200">
                      {candidate.contradictions} contradictions
                    </Badge>
                  )}
                </div>
                <p className="mt-2 text-sm text-slate-300">{candidate.summary}</p>
                <p className="mt-2 text-xs italic text-soft">{candidate.tradeoff}</p>
              </div>

              <div className="w-56 shrink-0 space-y-2">
                {candidate.dimensions.map((dimension) => (
                  <div key={dimension.dimension}>
                    <div className="mb-1 flex justify-between text-[10px] text-soft">
                      <span>{dimension.label}</span>
                      <span className="font-mono">
                        {Math.round(dimension.value * 100)}%
                      </span>
                    </div>
                    <Meter value={dimension.value} />
                  </div>
                ))}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function Pipeline({ candidates }: { candidates: CandidateSummary[] }) {
  const counts = STAGES.map((stage) => ({
    ...stage,
    count: candidates.filter((c) => c.stage === stage.key).length,
  }));

  return (
    <div>
      <SectionTitle hint="Stage is derived from the evidence rather than stored, so it cannot drift out of step with it. The terminal stages are reached by a recruiter, never by the system.">
        Application pipeline
      </SectionTitle>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {counts.map((stage) => (
          <div key={stage.key} className="card">
            <p className="eyebrow">{stage.label}</p>
            <p className="mt-2 text-2xl font-semibold text-white">{stage.count}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
