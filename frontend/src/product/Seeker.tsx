// The job seeker's side: browse, apply, watch the investigation, read the result.
//
// The investigation screen is the one that has to be honest. It renders the
// steps the backend reports and nothing else - no simulated progress, no step
// that ticks itself while the server is still working. When a stage is skipped
// it says skipped, and says why.

import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, watchInvestigation } from "./api";
import type { ApplicationRecord, Assessment, Investigation, Job } from "./api";
import {
  ConflictNotice,
  EvidenceGraph,
  ExternalEvidence,
  LevelBanner,
  Panel,
  Pill,
  RequirementRow,
  Timeline,
} from "./components";

function Loading({ what }: { what: string }) {
  return <p className="text-sm text-soft">Loading {what}...</p>;
}

function Failed({ error }: { error: string }) {
  return (
    <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-4">
      <p className="text-sm text-rose-200">{error}</p>
    </div>
  );
}

// --------------------------------------------------------------------------
// Browse
// --------------------------------------------------------------------------

function BrowseJobs() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.jobs().then(setJobs).catch((problem) => setError(problem.message));
  }, []);

  if (error) return <Failed error={error} />;
  if (!jobs) return <Loading what="open roles" />;

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold text-white">Open roles</h2>
        <p className="mt-1 text-sm text-soft">
          {jobs.length} published requisition{jobs.length === 1 ? "" : "s"}.
        </p>
      </header>

      {jobs.length === 0 ? (
        <p className="text-sm text-soft">
          No roles are published yet. A recruiter has to publish one first.
        </p>
      ) : null}

      <div className="grid gap-3">
        {jobs.map((job) => (
          <Link
            key={job.id}
            to={`/jobs/${job.id}`}
            className="rounded-xl border border-white/10 bg-panel/50 p-5 transition hover:border-accent/40 hover:bg-panel/80"
          >
            <div className="flex flex-wrap items-center gap-3">
              <h3 className="text-base font-semibold text-white">{job.title}</h3>
              <Pill className="bg-white/10 text-slate-300">{job.seniority}</Pill>
            </div>
            <p className="mt-1 text-sm text-soft">
              {job.company}
              {job.location ? ` - ${job.location}` : ""}
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {job.requiredSkills.map((spec) => (
                <Pill key={spec.skill} className="bg-accent/15 text-accent">
                  {spec.skill}
                </Pill>
              ))}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Job detail + apply
// --------------------------------------------------------------------------

function JobDetail() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [github, setGithub] = useState("");
  const [portfolio, setPortfolio] = useState("");
  const [name, setName] = useState("");

  useEffect(() => {
    api.job(jobId).then(setJob).catch((problem) => setError(problem.message));
  }, [jobId]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Attach your resume as a PDF or an image before submitting.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("job_id", jobId);
      form.append("candidate_name", name);
      form.append("github_url", github);
      form.append("portfolio_url", portfolio);
      form.append("resume", file);

      const record = await api.apply(form);
      await api.investigate(record.id);
      navigate(`/applications/${record.id}`);
    } catch (problem) {
      setError((problem as Error).message);
      setBusy(false);
    }
  }

  if (error && !job) return <Failed error={error} />;
  if (!job) return <Loading what="this role" />;

  return (
    <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
      <div className="space-y-4">
        <header>
          <h2 className="text-2xl font-semibold text-white">{job.title}</h2>
          <p className="mt-1 text-sm text-soft">
            {job.company}
            {job.location ? ` - ${job.location}` : ""} - {job.seniority}
          </p>
        </header>

        {job.description ? (
          <Panel title="About the role">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
              {job.description}
            </p>
          </Panel>
        ) : null}

        <Panel title="What this role screens against">
          <div className="space-y-2">
            {(job.requirements ?? []).map((requirement) => (
              <div
                key={requirement.id}
                className="flex flex-wrap items-center gap-2 border-b border-white/5 pb-2 last:border-0"
              >
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
                  <span className="text-xs text-soft">
                    {requirement.minYears}+ years
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </Panel>

        {job.conflicts?.length ? <ConflictNotice conflicts={job.conflicts} /> : null}
      </div>

      <Panel title="Apply" hint="Your resume is read, not keyword-matched.">
        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="eyebrow">Your name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="as it appears on your resume"
              className="mt-1 w-full rounded border border-white/15 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-accent"
            />
          </label>

          <label className="block">
            <span className="eyebrow">Resume (PDF or image, max 15 MB)</span>
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="mt-1 w-full rounded border border-white/15 bg-black/30 px-3 py-2 text-xs text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-accent/20 file:px-3 file:py-1 file:text-accent"
            />
          </label>

          <label className="block">
            <span className="eyebrow">GitHub URL (optional)</span>
            <input
              value={github}
              onChange={(event) => setGithub(event.target.value)}
              placeholder="https://github.com/yourname"
              className="mt-1 w-full rounded border border-white/15 bg-black/30 px-3 py-2 font-mono text-xs text-white outline-none focus:border-accent"
            />
          </label>

          <label className="block">
            <span className="eyebrow">Portfolio URL (optional)</span>
            <input
              value={portfolio}
              onChange={(event) => setPortfolio(event.target.value)}
              placeholder="https://yoursite.example"
              className="mt-1 w-full rounded border border-white/15 bg-black/30 px-3 py-2 font-mono text-xs text-white outline-none focus:border-accent"
            />
          </label>

          {error ? <p className="text-xs text-rose-300">{error}</p> : null}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-accent/90 disabled:opacity-50"
          >
            {busy ? "Submitting..." : "Submit and run AI Match & Verify"}
          </button>

          <p className="text-[11px] leading-relaxed text-soft">
            Links you provide are checked against their public source. A link
            that cannot be read is reported as unverified - it never counts
            against you.
          </p>
        </form>
      </Panel>
    </div>
  );
}

// --------------------------------------------------------------------------
// My applications
// --------------------------------------------------------------------------

function MyApplications() {
  const [records, setRecords] = useState<ApplicationRecord[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.applications().then(setRecords).catch((p) => setError(p.message));
  }, []);

  if (error) return <Failed error={error} />;
  if (!records) return <Loading what="your applications" />;

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-white">My applications</h2>
      {records.length === 0 ? (
        <p className="text-sm text-soft">
          You have not applied to anything yet.{" "}
          <Link to="/jobs" className="text-accent">
            Browse open roles
          </Link>
          .
        </p>
      ) : null}
      <div className="grid gap-3">
        {records.map((record) => (
          <Link
            key={record.id}
            to={`/applications/${record.id}`}
            className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-panel/50 p-4 transition hover:border-accent/40"
          >
            <span className="font-mono text-xs text-soft">{record.id}</span>
            <span className="text-sm text-white">{record.resumeFilename}</span>
            <Pill className="bg-white/10 text-slate-300">{record.status}</Pill>
            {record.levelLabel ? (
              <span className="ml-auto text-sm text-emerald-300">
                Level {record.level} - {record.levelLabel}
              </span>
            ) : null}
          </Link>
        ))}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// The signature screen: live investigation, then the result
// --------------------------------------------------------------------------

function ApplicationView() {
  const { applicationId = "" } = useParams();
  const [record, setRecord] = useState<ApplicationRecord | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [error, setError] = useState("");

  const loadAssessment = useCallback(async () => {
    try {
      setAssessment(await api.assessment(applicationId));
    } catch {
      /* not ready yet; the timeline explains where it is */
    }
  }, [applicationId]);

  useEffect(() => {
    let stop: (() => void) | undefined;

    api
      .application(applicationId)
      .then((current) => {
        setRecord(current);
        if (!current.investigationId) return undefined;
        return api.investigation(current.investigationId).then((first) => {
          setInvestigation(first);
          if (first.isTerminal) {
            void loadAssessment();
            return;
          }
          stop = watchInvestigation(first.id, (update) => {
            setInvestigation(update);
            if (update.isTerminal) void loadAssessment();
          });
        });
      })
      .catch((problem) => setError(problem.message));

    return () => stop?.();
  }, [applicationId, loadAssessment]);

  if (error) return <Failed error={error} />;
  if (!record) return <Loading what="your application" />;

  const running = investigation !== null && !investigation.isTerminal;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end gap-3">
        <div>
          <p className="eyebrow">EvidenceHire AI</p>
          <h2 className="text-2xl font-semibold text-white">
            Investigating {record.candidateName || "your application"}
          </h2>
        </div>
        <span className="ml-auto font-mono text-xs text-soft">
          {record.resumeFilename} - stored on {record.storageBackend}
        </span>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(320px,420px)_1fr]">
        <Panel
          title="Investigation"
          hint={
            running
              ? "Live from the backend. Each step advances only when its stage finishes."
              : "Completed run."
          }
        >
          {investigation ? (
            <>
              <div className="mb-4 h-1.5 w-full overflow-hidden rounded bg-white/10">
                <div
                  className="h-full rounded bg-accent transition-all duration-500"
                  style={{ width: `${Math.round(investigation.progress * 100)}%` }}
                />
              </div>
              <Timeline steps={investigation.steps} />
              {investigation.errorCode ? (
                <div className="mt-4 rounded border border-rose-500/40 bg-rose-500/10 p-3">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-rose-200">
                    {investigation.errorCode}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-rose-100">
                    {investigation.errorDetail}
                  </p>
                </div>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-soft">
              This application has not been investigated yet.
            </p>
          )}
        </Panel>

        <div className="space-y-5">
          {assessment ? (
            <>
              <LevelBanner
                level={assessment.level}
                label={assessment.levelLabel}
                supported={assessment.requiredSupported}
                total={assessment.requiredTotal}
              />

              <Panel
                title="Requirement matrix"
                hint="Each requirement judged on its own evidence. Open WHY for the reasoning."
              >
                {assessment.fits.map((fit) => (
                  <RequirementRow key={fit.requirementId} fit={fit} />
                ))}
              </Panel>

              <Panel
                title="Evidence graph"
                hint="Built only from relationships the engine actually found."
              >
                <EvidenceGraph
                  nodes={assessment.graph.nodes}
                  edges={assessment.graph.edges}
                />
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

              <Panel title="Document provenance">
                <dl className="grid grid-cols-2 gap-2 text-xs">
                  <dt className="text-soft">Source file</dt>
                  <dd className="text-slate-200">{assessment.sourceFilename}</dd>
                  <dt className="text-soft">Pages</dt>
                  <dd className="text-slate-200">{assessment.pageCount}</dd>
                  <dt className="text-soft">Read by</dt>
                  <dd className="text-slate-200">{assessment.extractors.join(", ")}</dd>
                  <dt className="text-soft">Content hash</dt>
                  <dd className="break-all font-mono text-[10px] text-slate-300">
                    {assessment.sourceHash}
                  </dd>
                </dl>
              </Panel>
            </>
          ) : running ? (
            <Panel>
              <p className="text-sm text-soft">
                The result appears here once the investigation finishes. Nothing
                is shown before the evidence has actually been read.
              </p>
            </Panel>
          ) : (
            <Panel>
              <p className="text-sm text-soft">
                No assessment was produced for this application.
              </p>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Seeker() {
  return (
    <Routes>
      <Route index element={<BrowseJobs />} />
      <Route path="jobs" element={<BrowseJobs />} />
      <Route path="jobs/:jobId" element={<JobDetail />} />
      <Route path="applications" element={<MyApplications />} />
      <Route path="applications/:applicationId" element={<ApplicationView />} />
      <Route path="*" element={<Navigate to="/jobs" replace />} />
    </Routes>
  );
}
