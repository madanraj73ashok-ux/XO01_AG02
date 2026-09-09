// Typed access to the product API.
//
// Every call carries the bearer token the session holds. Nothing here invents
// a fallback value when a request fails: a screen that cannot load its data
// says so rather than rendering a plausible-looking empty state.

export type Role = "RECRUITER" | "JOB_SEEKER";

export interface Config {
  authMode: string;
  authIsVerified: boolean;
  storeBackend: string;
  storeReason: string;
  fileBackend: string;
  fileReason: string;
}

export interface SkillSpec {
  skill: string;
  min_years: number | null;
}

export interface Conflict {
  kind: string;
  requirementIds: string[];
  detail: string;
  recommendation: string;
}

export interface Requirement {
  id: string;
  skill: string;
  necessity: "required" | "preferred";
  minYears: number | null;
  maxSalaryLpa: number | null;
  description: string;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  description: string;
  location: string;
  jobType: string;
  seniority: string;
  requiredSkills: SkillSpec[];
  preferredSkills: SkillSpec[];
  minYearsTotal: number | null;
  maxSalaryLpa: number | null;
  status: string;
  recruiterId: string;
  createdAt: string;
  publishedAt: string | null;
  requirements?: Requirement[];
  conflicts?: Conflict[];
}

export interface ApplicationRecord {
  id: string;
  jobId: string;
  candidateUid: string;
  candidateName: string;
  email: string;
  resumeFilename: string;
  resumeUrl: string;
  storageBackend: string;
  githubUrl: string;
  portfolioUrl: string;
  status: string;
  investigationId: string;
  createdAt: string;
  level: number | null;
  levelLabel: string | null;
  requiredSupported: number | null;
  requiredTotal: number | null;
}

export interface Step {
  key: string;
  label: string;
  state: "pending" | "active" | "done" | "failed" | "skipped";
  detail: string;
  at: string | null;
}

export interface Investigation {
  id: string;
  applicationId: string;
  jobId: string;
  state: string;
  isTerminal: boolean;
  progress: number;
  errorCode: string;
  errorDetail: string;
  documentId: string;
  startedAt: string;
  completedAt: string | null;
  steps: Step[];
}

export interface Why {
  verdict: string;
  evidence_level: string;
  reasons: string[];
  quotes: { section: string; text: string; note: string; weight: number }[];
  searched: string[];
  caveat: string;
}

export interface TerminologyFinding {
  requirement_id: string;
  required_skill: string;
  candidate_terms: string[];
  relationship: "EXACT" | "EQUIVALENT" | "RELATED" | "NOT_EQUIVALENT" | "UNKNOWN";
  explanation: string;
}

export interface Fit {
  requirementId: string;
  skill: string;
  necessity: "required" | "preferred";
  status: string;
  statusLabel: string;
  evidenceLevel: "E0" | "E1" | "E2" | "E3" | "E4";
  evidenceLabel: string;
  evidenceRank: number;
  matchKind: string;
  claimedStrength: string;
  isOverclaimed: boolean;
  isMet: boolean;
  confidence: number;
  confidenceFactors: { reason: string; delta: number }[];
  terminology: TerminologyFinding | null;
  why: Why;
}

export interface GraphNode {
  id: string;
  kind: string;
  label: string;
  evidenceLevel?: string;
  necessity?: string;
  status?: string;
  text?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: string;
  label?: string;
}

export interface ExternalCheck {
  target: string;
  kind: string;
  kindLabel: string;
  url: string;
  state: string;
  stateLabel: string;
  note: string;
  authenticated: boolean;
  canCorroborate: boolean;
  isNegativeEvidence: boolean;
  needsHumanReview: boolean;
  contentHash: string | null;
  observed: Record<string, unknown>;
  checkedAt: string;
}

export interface Assessment {
  applicationId: string;
  jobId: string;
  candidateName: string;
  level: number;
  levelLabel: string;
  summary: string;
  requiredTotal: number;
  requiredSupported: number;
  unaddressed: number;
  overclaims: number;
  documentId: string;
  sourceFilename: string;
  sourceHash: string;
  pageCount: number;
  extractors: string[];
  requisitionConflicts: Conflict[];
  fits: Fit[];
  terminology: TerminologyFinding[];
  contradictions: {
    kind: string;
    label: string;
    subject: string;
    claimText: string;
    claimSection: string;
    evidenceNote: string;
    assessment: string;
    confidenceEffect: string;
    flag: string;
    rendered: string;
  }[];
  external: ExternalCheck[];
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  sections: { kind: string; text: string }[];
  generatedAt: string;
}

export interface Coverage {
  requirementId: string;
  skill: string;
  necessity: string;
  satisfied: string[];
  satisfiedCount: number;
  totalCandidates: number;
  coverageRatio: number;
  isGap: boolean;
  conclusion: string;
  nearMisses: {
    applicationId: string;
    candidateName: string;
    evidenceLevel: string;
    note: string;
  }[];
  rendered: string;
}

export interface Review {
  job: Job;
  applications: number;
  assessed: number;
  message: string;
  shortlist: {
    applicationId: string;
    candidateName: string;
    rank: number;
    bestFit: string;
    tradeoff: string;
    strengths: string[];
    gaps: string[];
    risks: string[];
    level: number;
    levelLabel: string;
    dimensions: { dimension: string; label: string; value: number; detail: string }[];
  }[];
  coverage: Coverage[];
  gaps: Coverage[];
  matrix: {
    applicationId: string;
    candidateName: string;
    cells: {
      requirementId: string;
      skill: string;
      evidenceLevel: string;
      status: string;
    }[];
  }[];
}

const TOKEN_KEY = "evidencehire.token";

export function readToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function writeToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* a browser refusing storage should not break the in-memory session */
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = readToken();
  const headers = new Headers(init.headers ?? {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? body;
    } catch {
      /* keep the status text */
    }
    const error = new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail)
    ) as Error & { status: number; detail: unknown };
    error.status = response.status;
    error.detail = detail;
    throw error;
  }
  return (await response.json()) as T;
}

export const api = {
  config: () => request<Config>("/api/config"),

  session: (body: { name: string; email: string; role: Role }) =>
    request<{ uid: string; role: Role; home: string; name: string }>(
      "/api/auth/session",
      { method: "POST", body: JSON.stringify(body) }
    ),

  jobs: () => request<Job[]>("/api/jobs"),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  createJob: (body: unknown) =>
    request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(body) }),
  analyzeJob: (id: string) =>
    request<Job>(`/api/jobs/${id}/analyze`, { method: "POST" }),
  publishJob: (id: string, acknowledge: boolean) =>
    request<Job>(`/api/jobs/${id}/publish?acknowledge_conflicts=${acknowledge}`, {
      method: "POST",
    }),

  applications: (jobId?: string) =>
    request<ApplicationRecord[]>(
      jobId ? `/api/applications?job_id=${jobId}` : "/api/applications"
    ),
  application: (id: string) => request<ApplicationRecord>(`/api/applications/${id}`),
  apply: (form: FormData) =>
    request<ApplicationRecord>("/api/applications", { method: "POST", body: form }),
  investigate: (applicationId: string) =>
    request<Investigation>(`/api/applications/${applicationId}/investigate`, {
      method: "POST",
    }),

  investigation: (id: string) => request<Investigation>(`/api/investigations/${id}`),
  assessment: (applicationId: string) =>
    request<Assessment>(`/api/assessments/${applicationId}`),

  review: (jobId: string) => request<Review>(`/api/recruiter/jobs/${jobId}/review`),
  compare: (jobId: string, left: string, right: string) =>
    request<{
      leftId: string;
      rightId: string;
      verdict: string;
      lines: {
        dimension: string;
        label: string;
        leftValue: number;
        rightValue: number;
        stronger: string | null;
        detail: string;
      }[];
    }>(`/api/recruiter/compare?job_id=${jobId}&left=${left}&right=${right}`),
};

/** Live investigation updates. Falls back to polling if the stream drops. */
export function watchInvestigation(
  id: string,
  onUpdate: (investigation: Investigation) => void
): () => void {
  const token = encodeURIComponent(readToken());
  let closed = false;
  let poller: number | undefined;

  const source = new EventSource(`/api/investigations/${id}/stream?token=${token}`);

  source.onmessage = (event) => {
    if (closed) return;
    try {
      onUpdate(JSON.parse(event.data) as Investigation);
    } catch {
      /* a malformed frame is skipped rather than shown */
    }
  };

  source.onerror = () => {
    // The stream closes when the run finishes, which is not an error worth
    // showing. Poll on so a completed run is never left looking mid-flight.
    source.close();
    if (closed) return;
    poller = window.setInterval(async () => {
      try {
        const current = await api.investigation(id);
        onUpdate(current);
        if (current.isTerminal && poller) window.clearInterval(poller);
      } catch {
        if (poller) window.clearInterval(poller);
      }
    }, 1500);
  };

  return () => {
    closed = true;
    source.close();
    if (poller) window.clearInterval(poller);
  };
}
