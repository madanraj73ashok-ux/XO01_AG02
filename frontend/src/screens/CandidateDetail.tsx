import { useState } from "react";
import type { ReactNode } from "react";
import type { CandidateDetail as Detail, Fit } from "../types";
import {
  Badge,
  EvidenceBadge,
  Meter,
  Quote,
  SectionTitle,
  Stat,
  StatusBadge,
} from "../components/ui";

export default function CandidateDetail({
  data,
  onBack,
}: {
  data: Detail;
  onBack: () => void;
}) {
  const required = data.fits.filter((f) => f.necessity === "required");
  const preferred = data.fits.filter((f) => f.necessity === "preferred");

  return (
    <div className="space-y-8">
      <div>
        <button
          onClick={onBack}
          className="mb-4 font-mono text-xs text-soft hover:text-accent"
        >
          &larr; back to candidates
        </button>
        <p className="eyebrow">{data.stage.replace(/_/g, " ")}</p>
        <h1 className="mt-1 text-3xl font-semibold text-white">
          {data.applicationId} — {data.candidateName}
        </h1>
        <p className="mt-2 max-w-4xl text-sm text-slate-300">{data.summary}</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Required strong"
          value={`${data.requiredStrong} / ${data.requiredTotal}`}
        />
        <Stat label="Unaddressed" value={data.unaddressed} tone="text-rose-400" />
        <Stat
          label="Unsupported claims"
          value={data.overclaims}
          tone="text-amber-400"
        />
        <Stat
          label="Contradictions"
          value={data.contradictions.length}
          tone="text-amber-400"
        />
      </div>

      {data.contradictions.length > 0 && (
        <div>
          <SectionTitle hint="Conflicts found inside this one application. Every flag quotes the text that caused it; an absence is reported as an absence, never as a discovery.">
            Contradictions
          </SectionTitle>
          <div className="space-y-4">
            {data.contradictions.map((contradiction, index) => (
              <div
                key={index}
                className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-4"
              >
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Badge className="bg-amber-500/20 text-amber-200">
                    {contradiction.flag}
                  </Badge>
                  <span className="text-xs text-soft">{contradiction.label}</span>
                </div>

                <dl className="space-y-2 text-sm">
                  <Row label="Claim">
                    <span className="text-slate-100">
                      &ldquo;{contradiction.claimText}&rdquo;
                    </span>
                    <span className="ml-2 font-mono text-[10px] text-soft">
                      {contradiction.claimSection}
                    </span>
                  </Row>
                  <Row label="Evidence">
                    <span className="text-slate-300">
                      {contradiction.evidenceNote}
                    </span>
                  </Row>
                  {contradiction.counterEvidence.length > 0 && (
                    <div className="space-y-2 pl-24">
                      {contradiction.counterEvidence.map((item, i) => (
                        <Quote key={i} section={item.section} text={item.sourceText} />
                      ))}
                    </div>
                  )}
                  <Row label="Assessment">
                    <span className="text-slate-100">{contradiction.assessment}</span>
                  </Row>
                  <Row label="Confidence">
                    <span className="text-amber-300">
                      {contradiction.confidenceEffect}
                    </span>
                  </Row>
                </dl>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <SectionTitle hint="Expand any criterion to see the evidence, the reasoning and the confidence arithmetic behind the verdict.">
          Requirement assessment
        </SectionTitle>
        <div className="space-y-2">
          {required.map((fit) => (
            <FitRow key={fit.requirementId} fit={fit} />
          ))}
        </div>
        <p className="eyebrow mb-2 mt-6">Preferred</p>
        <div className="space-y-2">
          {preferred.map((fit) => (
            <FitRow key={fit.requirementId} fit={fit} />
          ))}
        </div>
      </div>

      <div>
        <SectionTitle hint="The candidate's own words, as submitted.">
          Application source
        </SectionTitle>
        <div className="grid gap-3 lg:grid-cols-2">
          {data.sections.map((section) => (
            <div key={section.kind} className="card">
              <p className="eyebrow">{section.kind}</p>
              <p className="mt-2 text-sm leading-relaxed text-slate-300">
                {section.text}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="w-20 shrink-0 font-mono text-[10px] uppercase tracking-wider text-soft">
        {label}
      </dt>
      <dd className="flex-1">{children}</dd>
    </div>
  );
}

function FitRow({ fit }: { fit: Fit }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="overflow-hidden rounded-lg border border-white/10 bg-panel/40">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left transition hover:bg-panel"
      >
        <span className="font-mono text-[10px] text-soft">{open ? "−" : "+"}</span>
        <span className="w-44 shrink-0 font-medium text-white">{fit.skill}</span>
        <StatusBadge status={fit.status} label={fit.statusLabel} />
        <EvidenceBadge level={fit.evidenceLevel} />
        {fit.matchKind === "equivalent" && (
          <Badge className="bg-sky-500/20 text-sky-200">equivalent wording</Badge>
        )}
        {fit.matchKind === "related" && (
          <Badge className="bg-rose-500/20 text-rose-200">adjacent only</Badge>
        )}
        {fit.isOverclaimed && (
          <Badge className="bg-amber-500/20 text-amber-200">
            claimed {fit.claimedStrength}
          </Badge>
        )}
        <span className="ml-auto w-28 shrink-0">
          <span className="mb-1 block text-right font-mono text-[10px] text-soft">
            confidence {Math.round(fit.confidence * 100)}%
          </span>
          <Meter value={fit.confidence} danger={fit.confidence === 0} />
        </span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-white/10 px-4 py-4">
          <div>
            <p className="eyebrow mb-2">Why</p>
            <ul className="space-y-1 text-sm text-slate-300">
              {fit.reasons.map((reason, i) => (
                <li key={i}>· {reason}</li>
              ))}
            </ul>
          </div>

          {fit.supporting.length > 0 && (
            <div>
              <p className="eyebrow mb-2">Evidence quoted from the application</p>
              <div className="space-y-2">
                {fit.supporting.map((item, i) => (
                  <Quote key={i} section={item.section} text={item.sourceText} />
                ))}
              </div>
            </div>
          )}

          {fit.closestEvidence.length > 0 && (
            <div className="rounded border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-sm text-rose-200">
              Closest thing found: {fit.closestEvidence.join(", ")} — adjacent
              technology, not the required capability.
            </div>
          )}

          <div>
            <p className="eyebrow mb-2">Confidence breakdown</p>
            <div className="space-y-1">
              {fit.confidenceFactors.map((factor, i) => (
                <div key={i} className="flex justify-between text-xs">
                  <span className="text-slate-300">{factor.reason}</span>
                  <span
                    className={`font-mono ${
                      factor.delta < 0 ? "text-rose-300" : "text-emerald-300"
                    }`}
                  >
                    {factor.delta > 0 ? "+" : ""}
                    {factor.delta.toFixed(2)}
                  </span>
                </div>
              ))}
              <div className="flex justify-between border-t border-white/10 pt-1 text-xs font-semibold">
                <span className="text-white">Confidence</span>
                <span className="font-mono text-white">
                  {fit.confidence.toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
