// The recruiter's side: author a requisition, see what is wrong with it,
// publish it, then review who applied.
//
// The publish flow deliberately refuses a requisition whose conflicts have not
// been acknowledged. The system does not resolve the conflict and does not
// ignore it - a person has to say they have seen it, which is the only thing
// "recruiter review required" can honestly mean.

import { useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api } from "./api";
import type { ApplicationRecord, Assessment, Job, Review } from "./api";
import {
  ConflictNotice,
  EvidenceBadge,
  EvidenceGraph,
  ExternalEvidence,
  LevelBanner,
  Panel,
  Pill,
  RequirementRow,
} from "./components";

function Failed({ error }: { error: string }) {
  return (
    <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-4">
      <p className="text-sm text-rose-200">{error}</p>
    </div>
  );
}

// --------------------------------------------------------------------------
// Requisition list
// --------------------------------------------------------------------------

function JobList() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.jobs().then(setJobs).catch((problem) => setError(problem.message));
  }, []);

  if (error) return <Failed error={error} />;
  if (!jobs) return <p className="text-sm text-soft">Loading requisitions...</p>;

  return (
    <div className="space-y-4">
      <header className="flex items-end">
        <div>
          <h2 className="text-xl font-semibold text-white">Requisitions</h2>
          <p className="mt-1 text-sm text-soft">{jobs.length} in total.</p>
        </div>
        <Link
          to="/recruiter/new"
          className="ml-auto rounded bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent/90"
        >
          Create job
        </Link>
      </header>

      <div className="grid gap-3">
        {jobs.map((job) => (
          <Link
            key={job.id}
            to={`/recruiter/jobs/${job.id}`}
            className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-panel/50 p-4 transition hover:border-accent/40"
          >
            <span className="text-sm font-semibold text-white">{job.title}</span>
            <span className="text-xs text-soft">{job.company}</span>
            <Pill
              className={
                job.status === "published"
                  ? "bg-emerald-500/15 text-emerald-200"
                  : "bg-white/10 text-slate-300"
              }
            >
              {job.status}
            </Pill>
            <span className="ml-auto font-mono text-[11px] text-soft">{job.id}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Create
// --------------------------------------------------------------------------

function CreateJob() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("Junior Robotics Software Engineer");
  const [company, setCompany] = useState("Tarang Automation");
  const [location, setLocation] = useState("Puducherry");
  const [seniority, setSeniority] = useState("junior");
  const [description, setDescription] = useState("");
  const [required, setRequired] = useState(
    "ROS 2, Python, Robotics, Cloud Deployment, Container Orchestration"
  );
  const [preferred, setPreferred] = useState("Computer Vision, Simulation");
  const [years, setYears] = useState("5");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function parse(value: string) {
    return value
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean)
      .map((skill) => ({ skill, min_years: null }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const job = await api.createJob({
        title,
        company,
        location,
        seniority,
        description,
        required_skills: parse(required),
        preferred_skills: parse(preferred),
        min_years_total: years.trim() ? Number(years) : null,
      });
      navigate(`/recruiter/jobs/${job.id}`);
    } catch (problem) {
      setError((problem as Error).message);
      setBusy(false);
    }
  }

  const field =
    "mt-1 w-full rounded border border-white/15 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-accent";

  return (
    <form onSubmit={submit} className="max-w-3xl space-y-4">
      <header>
        <h2 className="text-xl font-semibold text-white">Create a requisition</h2>
        <p className="mt-1 text-sm text-soft">
          Analysis runs the moment you save. Conflicts are surfaced, never
          silently resolved.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="eyebrow">Title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} className={field} />
        </label>
        <label className="block">
          <span className="eyebrow">Company</span>
          <input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            className={field}
          />
        </label>
        <label className="block">
          <span className="eyebrow">Location</span>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className={field}
          />
        </label>
        <label className="block">
          <span className="eyebrow">Seniority</span>
          <select
            value={seniority}
            onChange={(e) => setSeniority(e.target.value)}
            className={field}
          >
            {["intern", "junior", "mid", "senior", "lead"].map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="block">
        <span className="eyebrow">Required skills (comma separated)</span>
        <input
          value={required}
          onChange={(e) => setRequired(e.target.value)}
          className={field}
        />
      </label>

      <label className="block">
        <span className="eyebrow">Preferred skills (comma separated)</span>
        <input
          value={preferred}
          onChange={(e) => setPreferred(e.target.value)}
          className={field}
        />
      </label>

      <label className="block max-w-xs">
        <span className="eyebrow">Minimum professional experience (years)</span>
        <input value={years} onChange={(e) => setYears(e.target.value)} className={field} />
      </label>

      <label className="block">
        <span className="eyebrow">Description</span>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={4}
          className={field}
        />
      </label>

      {error ? <p className="text-xs text-rose-300">{error}</p> : null}

      <button
        type="submit"
        disabled={busy}
        className="rounded bg-accent px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-accent/90 disabled:opacity-50"
      >
        {busy ? "Saving..." : "Save and analyze requirements"}
      </button>
    </form>
  );
}

// --------------------------------------------------------------------------
// Requisition detail: conflicts, publish, applications, review
// --------------------------------------------------------------------------

function JobDetail() {
  const { jobId = "" } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() {
    try {
      const [current, records] = await Promise.all([
        api.job(jobId),
        api.applications(jobId),
      ]);
      setJob(current);
      setApplications(records);
      setReview(await api.review(jobId));
    } catch (problem) {
      setError((problem as Error).message);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  async function publish(acknowledge: boolean) {
    setNotice("");
    try {
      await api.publishJob(jobId, acknowledge);
      setNotice("Published. Candidates can now see this role.");
      await refresh();
    } catch (problem) {
      const detail = (problem as Error & { detail?: unknown }).detail;
      if (detail && typeof detail === "object" && "message" in detail) {
        setNotice(String((detail as { message: string }).message));
      } else {
        setNotice((problem as Error).message);
      }
    }
  }

  if (error) return <Failed error={error} />;
  if (!job) return <p className="text-sm text-soft">Loading requisition...</p>;

  const conflicts = job.conflicts ?? [];

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-white">{job.title}</h2>
          <p className="mt-1 text-sm text-soft">
            {job.company} - {job.seniority} - {job.status}
          </p>
        </div>
        {job.status !== "published" ? (
          <button
            onClick={() => publish(conflicts.length > 0)}
            className="ml-auto rounded bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent/90"
          >
            {conflicts.length ? "Acknowledge conflict and publish" : "Publish job"}
          </button>
        ) : (
          <Pill className="ml-auto bg-emerald-500/15 text-emerald-200">published</Pill>
        )}
      </header>

      {notice ? (
        <div className="rounded-lg border border-sky-500/40 bg-sky-500/10 p-3 text-sm text-sky-100">
          {notice}
        </div>
      ) : null}

      <ConflictNotice conflicts={conflicts} />

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Structured requirements">
          <div className="space-y-2">
            {(job.requirements ?? []).map((requirement) => (
              <div
                key={requirement.id}
                className="flex flex-wrap items-center gap-2 border-b border-white/5 pb-2 last:border-0"
              >
                <span className="font-mono text-[11px] text-soft">{requirement.id}</span>
                <Pill
                  className={
                    requirement.necessity === "required"
                      ? "bg-accent/15 text-accent"
                      : "bg-white/10 text-slate-300"
                  }
                >
                  {requirement.necessity}
                </Pill>
                <span className="text-sm text-white">{requirement.skill}</span>
                {requirement.minYears ? (
                  <span className="text-xs text-soft">{requirement.minYears}+ yrs</span>
                ) : null}
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title="Applications"
          hint={`${applications.length} received, ${review?.assessed ?? 0} assessed.`}
        >
          {applications.length === 0 ? (
            <p className="text-sm text-soft">Nobody has applied yet.</p>
          ) : (
            <div className="space-y-2">
              {applications.map((record) => (
                <Link
                  key={record.id}
                  to={`/recruiter/applications/${record.id}`}
                  className="flex flex-wrap items-center gap-2 rounded border border-white/5 p-2 transition hover:border-accent/40"
                >
                  <span className="text-sm text-white">
                    {record.candidateName || record.id}
                  </span>
                  <Pill className="bg-white/10 text-slate-300">{record.status}</Pill>
                  {record.levelLabel ? (
                    <span className="ml-auto text-xs text-emerald-300">
                      Level {record.level} - {record.levelLabel}
                    </span>
                  ) : null}
                </Link>
              ))}
            </div>
          )}
        </Panel>
      </div>

      {review && review.assessed > 0 ? (
        <>
          <div className="rounded-xl border border-white/10 bg-panel/40 p-5">
            <p className="eyebrow">Pool verdict</p>
            <p className="mt-2 text-lg font-semibold text-white">{review.message}</p>
          </div>

          <Panel
            title="Shortlist"
            hint="Ordered, but adjacent ranks usually mean different strengths rather than better and worse."
          >
            <div className="space-y-3">
              {review.shortlist.map((entry) => (
                <div key={entry.applicationId} className="rounded-lg bg-black/25 p-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-mono text-sm text-accent">#{entry.rank}</span>
                    <span className="text-sm font-semibold text-white">
                      {entry.candidateName}
                    </span>
                    <Pill className="bg-white/10 text-slate-300">
                      Level {entry.level} - {entry.levelLabel}
                    </Pill>
                    <Link
                      to={`/recruiter/applications/${entry.applicationId}`}
                      className="ml-auto font-mono text-[10px] uppercase tracking-wider text-accent"
                    >
                      open
                    </Link>
                  </div>
                  <p className="mt-2 text-sm text-slate-300">{entry.tradeoff}</p>
                  <div className="mt-2 grid gap-1 text-xs sm:grid-cols-3">
                    <p className="text-emerald-300">
                      Strong: {entry.strengths.join(", ") || "none"}
                    </p>
                    <p className="text-amber-300">
                      Gap: {entry.gaps.join(", ") || "none"}
                    </p>
                    <p className="text-rose-300">
                      Risk: {entry.risks.join(", ") || "none"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel
            title="Trade-off matrix"
            hint="Evidence level per requirement, per candidate."
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-soft">
                    <th className="p-2">Candidate</th>
                    {review.matrix[0]?.cells.map((cell) => (
                      <th key={cell.requirementId} className="p-2">
                        {cell.skill}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {review.matrix.map((row) => (
                    <tr key={row.applicationId} className="border-t border-white/5">
                      <td className="p-2 text-white">{row.candidateName}</td>
                      {row.cells.map((cell) => (
                        <td key={cell.requirementId} className="p-2">
                          <EvidenceBadge level={cell.evidenceLevel} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {review.gaps.length ? (
            <Panel
              title="Pool gaps"
              hint="A criterion nobody demonstrates is a fact about the requisition and the market."
            >
              <div className="space-y-3">
                {review.gaps.map((gap) => (
                  <pre
                    key={gap.requirementId}
                    className="overflow-x-auto rounded bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-amber-200"
                  >
                    {gap.rendered}
                  </pre>
                ))}
              </div>
            </Panel>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// One candidate, in full
// --------------------------------------------------------------------------

function CandidateView() {
  const { applicationId = "" } = useParams();
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .assessment(applicationId)
      .then(setAssessment)
      .catch((problem) => setError(problem.message));
  }, [applicationId]);

  if (error) return <Failed error={error} />;
  if (!assessment) return <p className="text-sm text-soft">Loading assessment...</p>;

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-2xl font-semibold text-white">{assessment.candidateName}</h2>
        <p className="mt-1 text-sm text-soft">{assessment.summary}</p>
      </header>

      <LevelBanner
        level={assessment.level}
        label={assessment.levelLabel}
        supported={assessment.requiredSupported}
        total={assessment.requiredTotal}
      />

      <Panel title="Requirement matrix" hint="Open WHY on any row.">
        {assessment.fits.map((fit) => (
          <RequirementRow key={fit.requirementId} fit={fit} />
        ))}
      </Panel>

      <Panel title="Terminology analysis" hint="Equivalent is not the same as related.">
        <div className="space-y-2">
          {assessment.terminology.map((finding) => (
            <div
              key={finding.requirement_id}
              className="border-b border-white/5 pb-2 text-xs last:border-0"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm text-white">{finding.required_skill}</span>
                <Pill
                  className={
                    finding.relationship === "RELATED" ||
                    finding.relationship === "NOT_EQUIVALENT"
                      ? "bg-amber-500/15 text-amber-200"
                      : finding.relationship === "UNKNOWN"
                        ? "bg-white/10 text-slate-300"
                        : "bg-emerald-500/15 text-emerald-200"
                  }
                >
                  {finding.relationship.replace("_", " ")}
                </Pill>
                {finding.candidate_terms.length ? (
                  <span className="font-mono text-[11px] text-soft">
                    candidate wrote: {finding.candidate_terms.join(", ")}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 leading-relaxed text-slate-300">{finding.explanation}</p>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Evidence graph">
        <EvidenceGraph nodes={assessment.graph.nodes} edges={assessment.graph.edges} />
      </Panel>

      <Panel title="External evidence">
        <ExternalEvidence checks={assessment.external} />
      </Panel>

      {assessment.contradictions.length ? (
        <Panel
          title="Discrepancies requiring verification"
          hint="Reported for human review. These are not accusations."
        >
          <div className="space-y-3">
            {assessment.contradictions.map((item, index) => (
              <pre
                key={`${item.kind}-${index}`}
                className="overflow-x-auto rounded bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-slate-300"
              >
                {item.rendered}
              </pre>
            ))}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

export default function Recruiter() {
  return (
    <Routes>
      <Route index element={<JobList />} />
      <Route path="new" element={<CreateJob />} />
      <Route path="jobs/:jobId" element={<JobDetail />} />
      <Route path="applications/:applicationId" element={<CandidateView />} />
    </Routes>
  );
}
