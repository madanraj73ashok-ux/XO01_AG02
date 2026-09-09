// Mirrors the JSON returned by the FastAPI layer in api.py.
// The engine remains the source of truth; these are transport shapes only.

export interface Dimension {
  dimension: string;
  label: string;
  value: number;
  detail: string;
}

export interface EvidenceItem {
  section: string;
  sourceText: string;
  note: string;
  weight?: number;
}

export interface ConfidenceFactor {
  reason: string;
  delta: number;
}

export interface Fit {
  requirementId: string;
  skill: string;
  necessity: "required" | "preferred";
  status: "strong" | "moderate" | "weak" | "unaddressed";
  statusLabel: string;
  evidenceLevel: "E0" | "E1" | "E2" | "E3" | "E4";
  evidenceLabel: string;
  evidenceRank: number;
  matchKind: "exact" | "equivalent" | "related" | "none";
  claimedStrength: string;
  isOverclaimed: boolean;
  isMet: boolean;
  confidence: number;
  confidenceFactors: ConfidenceFactor[];
  reasons: string[];
  closestEvidence: string[];
  supporting: EvidenceItem[];
}

export interface Contradiction {
  kind: string;
  label: string;
  subject: string;
  claimText: string;
  claimSection: string;
  evidenceNote: string;
  assessment: string;
  confidenceEffect: string;
  flag: string;
  counterEvidence: EvidenceItem[];
  rendered: string;
}

export interface CandidateSummary {
  applicationId: string;
  candidateName: string;
  rank: number;
  summary: string;
  bestFit: string;
  tradeoff: string;
  dimensions: Dimension[];
  requiredTotal: number;
  requiredStrong: number;
  unaddressed: number;
  overclaims: number;
  contradictions: number;
  stage: string;
}

export interface CandidateDetail {
  applicationId: string;
  candidateName: string;
  summary: string;
  requiredTotal: number;
  requiredStrong: number;
  unaddressed: number;
  overclaims: number;
  stage: string;
  sections: { kind: string; text: string }[];
  fits: Fit[];
  contradictions: Contradiction[];
  requisitionIssues: RequisitionIssue[];
}

export interface Requirement {
  id: string;
  skill: string;
  necessity: "required" | "preferred";
  minYears: number | null;
  maxSalaryLpa: number | null;
  description: string;
}

export interface Conflict {
  kind: string;
  requirementIds: string[];
  detail: string;
  recommendation: string;
}

export interface RequisitionIssue {
  kind: string;
  requirementIds: string[];
  detail: string;
  recommendation: string;
}

export interface Requisition {
  id: string;
  title: string;
  seniority: string;
  requirements: Requirement[];
  conflicts: Conflict[];
}

export interface NearMiss {
  applicationId: string;
  candidateName: string;
  evidenceLevel: string;
  note: string;
}

export interface Coverage {
  requirementId: string;
  skill: string;
  necessity: "required" | "preferred";
  satisfied: string[];
  satisfiedCount: number;
  totalCandidates: number;
  coverageRatio: number;
  isGap: boolean;
  conclusion: string;
  nearMisses: NearMiss[];
}

export interface Dashboard {
  requisitionTitle: string;
  requisitionId: string;
  applications: number;
  requisitionConflicts: number;
  poolGaps: number;
  gapSkills: string[];
  overclaims: number;
  contradictions: number;
  fullyQualified: number;
  fullRequisitionMessage: string;
  evidenceSpread: { level: string; count: number }[];
  coverage: Coverage[];
}

export interface ComparisonLine {
  dimension: string;
  label: string;
  leftValue: number;
  rightValue: number;
  stronger: string | null;
  detail: string;
}

export interface Comparison {
  leftId: string;
  rightId: string;
  verdict: string;
  lines: ComparisonLine[];
}

export interface ShortlistEntry {
  applicationId: string;
  candidateName: string;
  rank: number;
  bestFit: string;
  tradeoff: string;
  strengths: string[];
  gaps: string[];
  risks: string[];
  dimensions: Dimension[];
}
