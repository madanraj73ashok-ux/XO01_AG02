import { useEffect, useState } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import { api } from "../api";
import type { CandidateSummary, Comparison } from "../types";
import { SectionTitle } from "../components/ui";

export default function Compare({ candidates }: { candidates: CandidateSummary[] }) {
  const [left, setLeft] = useState(candidates[0]?.applicationId ?? "");
  const [right, setRight] = useState(candidates[1]?.applicationId ?? "");
  const [result, setResult] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!left || !right) return;
    setError(null);
    api
      .compare(left, right)
      .then(setResult)
      .catch((e: Error) => setError(e.message));
  }, [left, right]);

  const chartData =
    result?.lines.map((line) => ({
      axis: line.label,
      [result.leftId]: Math.round(line.leftValue * 100),
      [result.rightId]: Math.round(line.rightValue * 100),
    })) ?? [];

  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow">Head to head</p>
        <h1 className="mt-1 text-3xl font-semibold text-white">
          Candidate comparison
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-soft">
          Four independent axes, deliberately not averaged. Where both candidates
          lead somewhere, that is a trade-off — and the system says so rather than
          naming a winner.
        </p>
      </div>

      <div className="flex flex-wrap gap-4">
        <Picker label="Left" value={left} onChange={setLeft} options={candidates} />
        <Picker label="Right" value={right} onChange={setRight} options={candidates} />
      </div>

      {error && (
        <div className="rounded border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">
          {error}
        </div>
      )}

      {result && (
        <>
          <div className="rounded-lg border border-accent/40 bg-accent/5 p-5">
            <p className="eyebrow mb-2 text-accent">Verdict</p>
            <p className="text-sm leading-relaxed text-slate-100">{result.verdict}</p>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card">
              <SectionTitle>Shape of the difference</SectionTitle>
              <ResponsiveContainer width="100%" height={300}>
                <RadarChart data={chartData}>
                  <PolarGrid stroke="rgba(255,255,255,0.15)" />
                  <PolarAngleAxis
                    dataKey="axis"
                    tick={{ fill: "#7a8399", fontSize: 11 }}
                  />
                  <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                  <Radar
                    name={result.leftId}
                    dataKey={result.leftId}
                    stroke="#eb6c36"
                    fill="#eb6c36"
                    fillOpacity={0.25}
                  />
                  <Radar
                    name={result.rightId}
                    dataKey={result.rightId}
                    stroke="#38bdf8"
                    fill="#38bdf8"
                    fillOpacity={0.2}
                  />
                </RadarChart>
              </ResponsiveContainer>
              <div className="mt-2 flex gap-4 text-xs">
                <span className="text-accent">■ {result.leftId}</span>
                <span className="text-sky-400">■ {result.rightId}</span>
              </div>
            </div>

            <div className="space-y-3">
              {result.lines.map((line) => (
                <div key={line.dimension} className="card">
                  <div className="mb-2 flex items-baseline justify-between">
                    <p className="text-sm font-medium text-white">{line.label}</p>
                    <p className="font-mono text-xs text-soft">
                      {Math.round(line.leftValue * 100)}% vs{" "}
                      {Math.round(line.rightValue * 100)}%
                    </p>
                  </div>
                  <p className="text-xs text-slate-300">{line.detail}</p>
                  {line.stronger === null && (
                    <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-soft">
                      comparable — no material difference
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Picker({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: CandidateSummary[];
}) {
  return (
    <label className="block">
      <span className="eyebrow">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 block rounded border border-white/15 bg-panel px-3 py-2 text-sm text-white"
      >
        {options.map((option) => (
          <option key={option.applicationId} value={option.applicationId}>
            {option.applicationId} — {option.candidateName}
          </option>
        ))}
      </select>
    </label>
  );
}
