import type { Requirement, Requisition } from "../types";
import { Badge, SectionTitle } from "../components/ui";

export default function RequisitionView({ data }: { data: Requisition }) {
  const required = data.requirements.filter((r) => r.necessity === "required");
  const preferred = data.requirements.filter((r) => r.necessity === "preferred");

  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow">Requisition</p>
        <h1 className="mt-1 text-3xl font-semibold text-white">{data.title}</h1>
        <p className="mt-1 text-sm text-soft">
          {data.id} · advertised as {data.seniority}-level
        </p>
      </div>

      {data.conflicts.length > 0 && (
        <div>
          <SectionTitle hint="Found in the requisition itself. Reported for review, never silently resolved.">
            Requirement conflicts and restrictions
          </SectionTitle>
          <div className="space-y-3">
            {data.conflicts.map((conflict, index) => (
              <div
                key={index}
                className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4"
              >
                <div className="mb-2 flex items-center gap-2">
                  <Badge className="bg-amber-500/20 text-amber-200">
                    {conflict.requirementIds.join(", ")}
                  </Badge>
                  <span className="font-mono text-[10px] text-soft">
                    {conflict.kind}
                  </span>
                </div>
                <p className="text-sm text-slate-100">{conflict.detail}</p>
                <p className="mt-2 text-xs text-soft">{conflict.recommendation}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <RequirementColumn title="Required" items={required} emphasise />
        <RequirementColumn title="Preferred" items={preferred} />
      </div>
    </div>
  );
}

function RequirementColumn({
  title,
  items,
  emphasise = false,
}: {
  title: string;
  items: Requirement[];
  emphasise?: boolean;
}) {
  return (
    <div>
      <SectionTitle>{title}</SectionTitle>
      <div className="space-y-3">
        {items.map((requirement) => (
          <div key={requirement.id} className="card">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p
                  className={`text-sm ${
                    emphasise ? "font-semibold text-white" : "text-slate-200"
                  }`}
                >
                  {requirement.skill}
                </p>
                <p className="mt-1 text-xs text-soft">{requirement.description}</p>
              </div>
              <div className="shrink-0 text-right">
                <p className="font-mono text-[10px] text-soft">{requirement.id}</p>
                {requirement.minYears !== null && (
                  <p className="mt-1 font-mono text-xs text-amber-300">
                    {requirement.minYears}+ yrs
                  </p>
                )}
                {requirement.maxSalaryLpa !== null && (
                  <p className="mt-1 font-mono text-xs text-amber-300">
                    ≤ ₹{requirement.maxSalaryLpa} LPA
                  </p>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
