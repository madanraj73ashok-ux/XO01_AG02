# EvidenceHire — Full System Build Plan for Claude

## Mission

Build EvidenceHire into a **complete, working, presentation-ready, two-sided AI talent-acquisition platform**. Do not redesign only the recruiter analytics dashboard. The finished product must demonstrate the complete journey from recruiter job creation to candidate application, document ingestion, AI investigation, evidence verification, explainable assessment, and recruiter shortlist/comparison.

Core journey:

```text
Recruiter → Create Job → Analyze Requirements → Publish
Candidate → Discover Job → Apply → Upload Resume
→ AI Match & Verify → Investigation Timeline
→ PDF/Image OCR & Parsing → Structured Candidate Data
→ Structured Job Data → Claims → Terminology
→ Evidence Investigation → Local ~0.6B LLM Reasoning
→ Deterministic Evidence Engine → E0–E4
→ Unsupported Claims / Contradictions / Gaps
→ Explainable Result → Recruiter Review / Shortlist / Trade-offs
```

## 1. Non-negotiable rules

- Build the **entire integrated system**, not a partial dashboard.
- Do not repeat the previous mistake of building UI that is disconnected from the actual workflow.
- Do not fabricate functionality or fake AI progress.
- Do not claim OCR, Scrapling, GitHub, Firebase, Cloudinary, or LLM integration is complete unless actually executed and verified.
- Preserve the existing Challenge 01 and Challenge 02 engine.
- Reuse working modules instead of rewriting them unnecessarily.
- Every important result must be traceable to evidence.
- Never fabricate evidence.
- Never accuse a candidate of lying solely because evidence is missing.
- Distinguish `NO_EVIDENCE` from `UNABLE_TO_VERIFY`.
- Distinguish `EQUIVALENT` from `RELATED`.
- Human recruiter remains responsible for the hiring decision.

## 2. Existing stable foundation

Current verified checkpoint:

```text
3de559d feat: complete PS02 surprise challenges 01 and 02
```

Parent:

```text
11e52a5 Add files via upload
```

Existing verified capabilities to preserve:

- Requirement extraction
- Requirement conflict detection
- Equivalent terminology
- Claim extraction
- E0–E4 evidence levels
- Requirement assessment
- Unsupported claims
- Contradiction detection
- Candidate trade-offs
- Pool gaps
- Explainable shortlist
- Explicit `No candidate fully satisfies all required criteria.` handling

Before changing code:

1. Inspect repository.
2. Run current backend tests.
3. Run frontend production build.
4. Inspect current routes and components.
5. Identify Firebase state.
6. Identify Cloudinary state.
7. Identify OCR state.
8. Identify Scrapling state.
9. Identify local LLM state.
10. Produce a short gap report.

Then implement. Do not blindly rewrite.

## 3. Technology architecture

### Frontend

- React
- Vite
- TypeScript
- Existing UI stack and routing where practical

### Backend

- Python
- FastAPI
- Existing `engine/` modules

### Authentication

- Firebase Authentication
- Roles: `RECRUITER`, `JOB_SEEKER`

### Database

- Firebase Firestore

### File storage

- Cloudinary for resume PDFs, images, and supported documents
- Store metadata/references in Firestore, not large binaries

### Document processing

- PaddleOCR for image/scanned text where applicable
- PyMuPDF/existing extraction for text PDFs

### External evidence

- GitHub public/API verification as the first complete source
- Scrapling for permitted public web extraction where useful

### LLM

- Local approximately **0.6B-parameter model**
- Exact model/runtime configurable through environment variables
- Example configuration: `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL`, `LOCAL_LLM_TIMEOUT`

The LLM is the reasoning/investigation layer, not the source of truth.

## 4. Architecture principle

Use:

```text
COLLECTION
  ↓
EXTRACTION / NORMALIZATION
  ↓
STRUCTURED DATA
  ↓
LLM INVESTIGATION PLANNING
  ↓
TOOLS COLLECT EVIDENCE
  ↓
DETERMINISTIC EVIDENCE ENGINE
  ↓
EXPLAINABLE ASSESSMENT
```

Do not use:

```text
Everything → LLM → score
```

The LLM may decide what to inspect next. Tools return actual data. Deterministic logic evaluates evidence.

## 5. Two-sided product

### Landing page

Message:

> **EvidenceHire — Don't just read what candidates claim. Verify what the evidence supports.**

Entry points:

```text
[I'm a Recruiter]
[I'm a Job Seeker]
```

### Recruiter portal

Navigation:

```text
Overview
Jobs
Create Job
Applications
Shortlist
Comparison
```

Recruiter can:

- Create/upload job description
- Analyze requirements
- Review conflicts
- Publish job
- Receive applications
- View evidence-based assessments
- View unsupported claims and contradictions
- Review pool gaps
- Compare candidates
- Review trade-offs

### Job seeker portal

Navigation:

```text
Available Jobs
My Applications
My Assessments
Profile
```

Candidate can:

- View published jobs
- Open job details
- Apply
- Upload PDF/image/document resume
- Optionally provide GitHub/portfolio URL
- Trigger `AI Match & Verify`
- View investigation progress
- View final evidence-based result

## 6. Firebase authentication

Implement real authentication.

Suggested user document:

```text
users/{uid}
{
  uid,
  name,
  email,
  role,
  photoURL,
  createdAt,
  updatedAt
}
```

Route based on role:

```text
RECRUITER   → /recruiter
JOB_SEEKER  → /jobs
```

Protect backend APIs as well as frontend routes. Never expose Firebase private credentials in the frontend.

## 7. Firestore model

Suggested collections:

```text
users/
jobs/
applications/
assessments/
evidence/
investigations/
activity/
```

Relationship:

```text
user → job → application → investigation → assessment → evidence
```

Keep raw input separate from normalized/derived information.

## 8. Cloudinary

Candidate upload flow:

```text
Candidate
  ↓
Upload Resume
  ↓
Cloudinary
  ↓
Document URL/reference
  ↓
Firestore application metadata
  ↓
Backend ingestion
```

Handle:

- Upload success
- Invalid file type
- File too large
- Cloudinary failure
- Processing failure

Never commit credentials.

## 9. Recruiter job creation

Create job fields:

- Title
- Company
- Description
- Required skills
- Preferred skills
- Experience
- Seniority
- Salary where applicable
- Location
- Job type

Support pasting/uploading a job description where the implementation permits.

Then:

```text
Analyze Requirements
```

Produce structured:

```text
Required
Preferred
Experience
Seniority
Salary
Constraints
```

## 10. Requirement conflict handling

Preserve Challenge 02 and make the result visible.

Example:

```text
Junior
+
5+ years experience
```

Show:

```text
⚠ REQUISITION CONFLICT

Junior role requires 5+ years experience.

Status:
RECRUITER REVIEW REQUIRED
```

Do not silently relax either requirement. Recruiter may edit/keep/dismiss the warning.

## 11. Publish job

After review:

```text
[Publish Job]
```

Suggested job record:

```text
jobs/{jobId}
{
  title,
  company,
  description,
  structuredRequirements,
  recruiterId,
  status,
  createdAt,
  updatedAt,
  publishedAt
}
```

Published jobs appear to job seekers.

## 12. Job seeker application

Job detail shows:

```text
Role
Company
Required skills
Preferred skills
Experience
Location

[Apply Now]
```

Application screen:

```text
Personal Information
Resume
Supporting Documents
GitHub URL (optional)
Portfolio URL (optional)

[Submit Application]
```

Store application metadata in Firestore and files in Cloudinary.

## 13. AI Match & Verify

After submission, provide:

```text
[AI MATCH & VERIFY]
```

This opens the signature AI investigation screen.

Do not immediately show only a score.

## 14. AI investigation screen

Make this one of the most polished screens.

Example:

```text
EVIDENCEHIRE AI
Investigating Rahul Kumar

✓ Application received
✓ Document detected
✓ Text extracted
✓ Candidate profile structured
✓ Job requirements understood
✓ Terminology normalized
⟳ Candidate claims identified
○ Evidence verification
○ External evidence
○ Requirement assessment
○ Final assessment
```

The progress state should reflect real backend stages/events, not a fake animation.

Suggested investigation states:

```text
RECEIVED
EXTRACTING
STRUCTURING
ANALYZING
INVESTIGATING
VERIFYING
ASSESSING
COMPLETE
FAILED
```

## 15. Document ingestion

Pipeline:

```text
Upload
 ↓
Cloudinary
 ↓
Document detection
 ↓
Text extraction / OCR
 ↓
Section detection
 ↓
Structured candidate profile
```

### Text PDF

Use PyMuPDF/existing extraction where text is available.

### Image

Use PaddleOCR.

### Scanned PDF

Where supported:

```text
PDF → render pages → OCR → text → sections → structure
```

Do not claim scanned-PDF OCR is complete until actually tested.

## 16. Structured candidate profile

Canonical structure:

```json
{
  "identity": {},
  "education": [],
  "experience": [],
  "skills": [],
  "projects": [],
  "certifications": [],
  "public_profiles": [],
  "claims": []
}
```

Important extracted facts must preserve provenance:

- source document
- section/page where available
- source span/text
- extraction method

## 17. Structured job profile

Canonical structure:

```json
{
  "role": "",
  "required": [],
  "preferred": [],
  "experience": {},
  "seniority": "",
  "salary": {},
  "constraints": []
}
```

Preserve original job text separately.

## 18. Claim extraction

Extract candidate assertions such as:

```text
"Expert in AWS"
"I have 4 years of Python experience"
"Proficient in ROS 2"
```

Each claim should retain:

- claim text
- claim type
- related requirement
- source
- source span
- asserted strength

Always distinguish candidate claims from verified evidence.

## 19. Terminology normalization — critical evaluator requirement

Return explicit relationships:

```text
EXACT
EQUIVALENT
RELATED
NOT_EQUIVALENT
UNKNOWN
```

Examples:

```text
ROS 2 ≈ Robot Operating System 2 ≈ ROS2 ≈ ROS 2 Humble
ML ≈ Machine Learning
Kubernetes ≈ K8s
```

But:

```text
Arduino ≠ ROS 2
```

Most importantly:

```text
Container Orchestration ↔ ECS
```

must **not** automatically become `EQUIVALENT`.

It may be `RELATED`, after which evidence must be examined.

This directly addresses the previous evaluator question.

## 20. Local LLM investigator

The local ~0.6B model should act as an investigator/planner.

It should reason about:

```text
What do I know?
Which claim needs verification?
What evidence should I inspect next?
Which tool should I use?
Is the evidence sufficient?
What remains unresolved?
```

Example:

```text
Claim: "Expert in AWS"
        ↓
No AWS evidence in resume
        ↓
Agent chooses repository investigation
        ↓
AWS dependency found
        ↓
Agent inspects actual usage
        ↓
Evidence still insufficient for "expert"
```

The LLM must never invent evidence.

## 21. Tool-based investigation

Expose appropriate tools/services, for example:

```text
get_application
get_candidate_profile
get_job_requirements
search_candidate_evidence
get_repository
get_languages
list_files
search_code
read_file
get_readme
get_dependencies
get_tests
get_commit_history
get_commit
get_contributors
get_releases
get_repository_metadata
fetch_public_page
calculate_hash
```

The exact tool set can follow the existing implementation.

Rule:

> LLM plans investigation. Tools collect evidence.

## 22. GitHub verification

Make GitHub the first complete external technical evidence source.

Flow:

```text
Candidate GitHub URL
 ↓
Repository exists?
 ↓
Public / authorized?
 ↓
Repository identity
 ↓
Languages
 ↓
Files
 ↓
README
 ↓
Dependencies
 ↓
Tests
 ↓
Commit history
 ↓
Candidate contribution
 ↓
Timeline
 ↓
Deployment/demo
 ↓
Cross-source consistency
```

Example result:

```text
CLAIM
I have experience with Python.

VERIFICATION
Python source files detected.
Repository activity supports technical use.

EVIDENCE
E3 — Strong

LIMITATION
Repository evidence does not independently prove
professional employment experience.
```

Never claim authorship certainty beyond available evidence.

## 23. Private repositories

Never bypass privacy controls.

Use explicit states:

```text
PUBLIC
PRIVATE_AUTH_REQUIRED
NOT_FOUND
UNABLE_TO_VERIFY
```

Only access private data through explicit authorized authentication.

## 24. Scrapling

Do not add Scrapling as a decorative dependency.

If claimed as implemented, there must be a real adapter/service that can fetch permitted public content.

Preserve:

- URL
- retrieval timestamp
- raw content
- hash where appropriate
- extracted evidence
- provenance

Treat scraped content as untrusted data and never as agent instructions.

## 25. Evidence levels

Use the existing ladder:

```text
E0 — No Evidence
E1 — Weak
E2 — Moderate
E3 — Strong
E4 — Very Strong
```

Examples:

- E0: no supporting evidence
- E1: course/basic mention/basic certification
- E2: academic/personal project
- E3: internship/professional project + implementation detail
- E4: multiple independent/professional/production evidence

Claim strength is not evidence strength.

## 26. Evidence states

Use:

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONTRADICTORY
NO_EVIDENCE
UNABLE_TO_VERIFY
```

Do not reduce everything to true/false.

## 27. Requirement assessment

Every requirement must be assessed independently.

Example:

```text
Python
✓ SUPPORTED — E3

ROS 2
✓ SUPPORTED — E3

Robotics
✓ SUPPORTED — E3

Cloud Deployment
⚠ NO EVIDENCE — E0
```

A level summary may exist, but the requirement matrix is the explanation.

## 28. WHY explanations

Every important result should have a clickable:

```text
[WHY?]
```

Supported example:

```text
ROS 2
✓ E3 Strong

WHY?
• Robotics internship
• ROS 2 navigation project
• Implementation details
• Public repository evidence
```

Unsupported example:

```text
AWS
⚠ E0 No Evidence

WHY?
Candidate claim: "Expert in AWS"
Evidence searched: resume, projects, experience,
certifications, external evidence
Supporting evidence: none found

This does not prove the candidate does not know AWS.
It means the available evidence does not currently support the claim.
```

## 29. Challenge 01 contradiction detection

Preserve and integrate existing logic.

Example:

```text
Claim: 5 years Python experience
Evidence: approximately 0.9 years evidenced
Result: duration discrepancy / insufficiently supported
```

Use careful language. Do not turn missing evidence into an accusation.

## 30. Challenge 02 requirements/trade-offs

Preserve:

- requirement conflicts
- unmet requirements
- candidate near-misses
- multi-dimensional shortlist
- trade-offs
- pool gaps
- explicit no-full-match message

If applicable:

```text
No candidate fully satisfies all required criteria.
```

## 31. Shortlist

Do not produce fake precision such as `87.3%` as the primary decision.

Use evidence-supported levels and requirement coverage.

Example:

```text
#1 Rahul Kumar
LEVEL 4 — STRONGLY SUPPORTED

4 / 5 required criteria supported
Main strength: ROS 2 + Robotics
Main gap: Cloud deployment
```

## 32. Trade-off comparison

Example:

```text
             Rahul       Priya       Arjun
Python         E4          E3          E3
ROS 2          E3          E3          E2
Robotics       E3          E2          E3
Vision         E3          E2          E1
Cloud          E0          E0          E2
```

Then explain the trade-off in plain language.

Do not automatically declare a universal winner.

## 33. Pool gap

If no candidate demonstrates a required criterion:

```text
POOL GAP
Cloud Deployment
0 / 12 candidates demonstrated this requirement.

No candidate fully satisfies all required criteria.
```

## 34. Evidence graph — signature UI

Create a visually distinctive graph connecting:

```text
Candidate
Claim
Requirement
Project
Repository
Commit
Certification
Publication
Portfolio
Deployment
```

Relationships:

```text
CLAIMS
SUPPORTS
CONTRADICTS
EQUIVALENT_TO
RELATED_TO
USED_IN
DEPLOYED_AS
CONTRIBUTED_TO
VERIFIED_BY
```

Example:

```text
Candidate
  │
  └── CLAIMS → Python
                  │
                  └── SUPPORTS ← Project
                                   │
                                   └── USED_IN → GitHub Repo
```

Clicking a node should reveal evidence/provenance.

## 35. UI direction

The UI should feel like **AI Investigation + Evidence Intelligence**, not another generic ATS.

Prioritize:

- investigation timeline
- evidence cards
- evidence ladder
- WHY panels
- requirement matrix
- evidence graph
- source provenance
- candidate result
- recruiter trade-offs

Avoid meaningless percentages and decorative AI animations that are disconnected from real state.

Optimize the main presentation view for approximately 1366×768 and 1440×900.

## 36. Candidate final result

Example:

```text
YOUR EVIDENCEHIRE RESULT

LEVEL 3 — WELL SUPPORTED

Python              ✓ E3
ROS 2               ✓ E3
Robotics            ✓ E3
Computer Vision     ✓ E2
Cloud Deployment    ⚠ E0

Evidence Coverage: 4 / 5
Unsupported Claims: 1
Discrepancies: 0

[View Why]
[View Evidence]
```

## 37. Recruiter dashboard

The dashboard is the final review surface, not the entire product.

Example:

```text
EvidenceHire

Active Requisition
Junior Robotics Software Engineer

Applications       12
Strongly Supported 4
Pool Gaps           1
Unsupported Claims  8
Discrepancies       18

⚠ Requisition Issue
Junior + 5+ years

⚠ Pool Gap
Cloud Deployment — 0 / 12

Shortlist
1. Candidate A — Level 4
2. Candidate B — Level 3
3. Candidate C — Level 3
```

## 38. API integration

Reuse existing routes where possible. Suggested capabilities:

```text
POST /api/jobs
GET  /api/jobs
GET  /api/jobs/{jobId}
POST /api/jobs/{jobId}/analyze
POST /api/jobs/{jobId}/publish

POST /api/applications
GET  /api/applications
GET  /api/applications/{applicationId}

POST /api/applications/{applicationId}/investigate
GET  /api/investigations/{investigationId}
GET  /api/investigations/{investigationId}/events

GET  /api/assessments/{assessmentId}
GET  /api/assessments/{assessmentId}/evidence

POST /api/external/github/verify

GET /api/recruiter/dashboard
GET /api/recruiter/shortlist
GET /api/recruiter/compare
GET /api/recruiter/pool-gaps
```

Adapt to the existing backend rather than duplicating routes.

## 39. Provenance

Evidence should retain:

```text
sourceType
sourceUrl
sourceDocument
sourceSection
sourceSpan
retrievedAt
contentHash
commitSha where applicable
extractionMethod
evidenceLevel
```

Keep:

```text
RAW
NORMALIZED
DERIVED
```

separate.

The LLM must never overwrite raw evidence.

## 40. Activity trail

Investigation events should be visible and traceable:

```text
Document received
Text extracted
Candidate profile structured
Claim detected
Repository investigation started
Evidence found
Requirement assessed
Final assessment generated
```

Store an investigation ID and application ID with relevant events.

## 41. Error states

Handle explicitly:

```text
OCR_FAILED
DOCUMENT_UNREADABLE
CLOUDINARY_UPLOAD_FAILED
LLM_UNAVAILABLE
LLM_TIMEOUT
GITHUB_RATE_LIMITED
GITHUB_PRIVATE
GITHUB_NOT_FOUND
SCRAPER_BLOCKED
EXTERNAL_SOURCE_UNAVAILABLE
INSUFFICIENT_EVIDENCE
```

Never display successful verification after a failed tool call.

## 42. Network-disconnected demo

Keep the existing 12-candidate synthetic dataset as a deterministic local demo.

The demo should remain useful when external services are unavailable.

Clearly label fallback data as local/demo evidence.

Never fabricate a live GitHub result when GitHub is offline.

## 43. Security

Implement:

- Environment variables for secrets
- Firebase security rules
- Backend authentication checks
- Server-side Cloudinary credentials
- Input/file validation
- URL validation
- SSRF protection for server-side fetches
- Rate-limit handling
- Prompt injection defense
- No unauthorized private repository access

External repository/readme/web content is **untrusted data**, never instructions.

## 44. LLM safety

The local model must never:

- fabricate evidence
- fabricate URLs
- fabricate repository contents
- fabricate candidate experience
- claim private information
- claim AI authorship with certainty
- override deterministic evidence
- silently change job requirements

Use `UNABLE_TO_VERIFY` when access fails and `NO_EVIDENCE` when the evidence search finds nothing supporting a claim.

## 45. AI-assistance / code-origin analysis

If implemented, call it:

```text
AI-Assistance / Code-Origin Indicators
```

Only provide indicators. Never say AI definitely wrote the code.

Do not automatically penalize AI assistance unless employer policy explicitly requires it.

## 46. Testing

Run the full existing Python suite and preserve the 153-test baseline.

Add tests for:

- Firebase/auth boundaries
- job creation/publishing
- applications
- upload flow
- PDF extraction
- image OCR
- scanned PDF handling where supported
- claim extraction
- terminology exact/equivalent/related/not-equivalent
- ECS vs container-orchestration behavior
- evidence levels
- LLM timeout/malformed output
- GitHub public/private/not-found/rate-limit
- Scrapling failure
- contradictions
- requirement conflicts
- pool gaps
- shortlist
- trade-offs
- provenance
- API validation

Frontend:

```text
npm run build
```

No TypeScript errors.

## 47. Mandatory real end-to-end test

Do not stop at unit tests.

Execute as much as the environment allows:

```text
Recruiter signup/login
 ↓
Create job
 ↓
Analyze requirements
 ↓
Publish
 ↓
Candidate signup/login
 ↓
View job
 ↓
Apply
 ↓
Upload actual test resume
 ↓
Cloudinary
 ↓
PDF/image processing
 ↓
Structured candidate
 ↓
Local LLM investigation
 ↓
Evidence assessment
 ↓
Candidate result
 ↓
Recruiter sees application
 ↓
Recruiter sees evidence
 ↓
Shortlist
 ↓
Comparison
 ↓
Trade-offs
```

If a service cannot be tested, state exactly which step was blocked and why.

## 48. Acceptance criteria

### Firebase

- Signup works.
- Signin works.
- Role persists.
- Correct portal opens.
- Firestore persistence works.
- Security rules exist.

### Cloudinary

- Resume uploads.
- URL/reference persists.
- Backend processes uploaded file.
- Failure is handled.

### OCR

Complete only if an actual image can be uploaded, OCR runs, text is extracted, structured data is produced, and the assessment consumes it.

### PDF

Complete only if an actual PDF can be uploaded, extracted, structured, and assessed.

### Scrapling

Complete only if a real permitted public page can be fetched, raw content preserved, relevant evidence extracted, provenance stored, and the evidence reaches assessment.

### Local LLM

Complete only if the actual local model endpoint is called, output is validated, investigation decisions can be represented, timeouts are handled, and evidence remains grounded.

### Product

The full recruiter → candidate → AI → recruiter journey must work.

## 49. Implementation order

### Phase 0 — Audit

Inspect and report gaps. No unnecessary redesign.

### Phase 1 — Firebase + persistence

Authentication, Firestore, Cloudinary, environment configuration, API auth.

### Phase 2 — Recruiter

Create job, requirement extraction, conflict review, publish.

### Phase 3 — Job seeker

Jobs, detail, apply, upload, application persistence.

### Phase 4 — Document pipeline

Cloudinary retrieval, PDF extraction, image OCR, structured candidate profile, provenance.

### Phase 5 — Local AI investigator

LLM adapter, investigation state machine, claim extraction, terminology analysis, evidence tool calls, grounded explanations.

### Phase 6 — External evidence

GitHub verification first; Scrapling public-source integration where useful.

### Phase 7 — Assessment integration

Integrate existing Challenge 01/02, evidence ladder, unsupported claims, contradictions, trade-offs, pool gaps.

### Phase 8 — Signature UI

Investigation timeline, evidence cards, WHY panels, evidence graph, requirement matrix, result, recruiter detail, comparison.

### Phase 9 — Hardening

Tests, security, failures, rate limits, network fallback.

### Phase 10 — Presentation

Polish, seed demo, verify startup commands, verify complete demo journey, update README.

## 50. Hero demo scenarios

Build and verify these because they directly answer evaluator questions.

### Scenario A — Unsupported AWS claim

```text
Claim: "Expert in AWS"
Resume evidence: none
External evidence: limited/insufficient
Result: E0 or insufficiently supported
```

### Scenario B — Equivalent terminology

```text
Job: ROS 2
Resume: Robot Operating System 2
Result: EQUIVALENT
```

### Scenario C — Related but not equivalent

```text
Job: Container Orchestration
Candidate: AWS ECS
Result: RELATED — NOT AUTOMATICALLY EQUIVALENT
Then inspect evidence.
```

### Scenario D — Requisition conflict

```text
Junior + 5+ years
Result: REQUISITION CONFLICT
Requires recruiter review.
```

### Scenario E — Pool gap

```text
Cloud Deployment
0 / 12
No candidate fully satisfies all required criteria.
```

## 51. Presentation-ready UX story

The judge should understand the product in 30 seconds:

```text
Recruiter publishes job.
Candidate applies.
Candidate uploads resume.
EvidenceHire investigates it.
The system checks claims against evidence.
The result explains WHY.
Recruiter sees transparent trade-offs.
```

Recommended five-minute demo:

```text
0:00–0:30  Problem: keyword matching vs evidence
0:30–1:00  Job seeker: job → apply → upload
1:00–1:45  AI investigation timeline
1:45–2:45  Evidence + WHY + terminology distinction
2:45–3:30  Contradiction / requisition conflict
3:30–4:15  Recruiter applications + shortlist
4:15–5:00  Evidence graph + pool gap + closing message
```

Closing line:

> **EvidenceHire doesn't ask only whether a candidate matches the job. It asks whether the candidate's claims are actually supported by evidence.**

## 52. Final definition of done

Do not declare completion until:

- Recruiter authentication works.
- Candidate authentication works.
- Recruiter can create/publish jobs.
- Candidate can discover/apply.
- Resume upload works.
- Cloudinary works.
- PDF extraction works.
- Image OCR works.
- Structured candidate data works.
- Structured job data works.
- Claims work.
- Terminology classification works.
- Local LLM is actually called.
- Investigation states work.
- Evidence verification works.
- GitHub verification works if configured.
- Scrapling works if claimed.
- E0–E4 work.
- Requirement matrix works.
- Unsupported claims work.
- Contradictions work.
- Requirement conflicts work.
- Pool gaps work.
- Shortlist works.
- Trade-offs work.
- WHY explanations work.
- Evidence graph works at least in a functional first version.
- Firestore persistence works.
- Security boundaries exist.
- Existing tests remain passing.
- New tests pass.
- React build passes.
- No secrets are committed.
- End-to-end demo is actually executed.

## 53. Final Claude reporting format

At the end, report:

```text
GIT
Current commit:
Branch:
Working tree:

TESTS
Python: X passed / X total
React build: PASS/FAIL

FIREBASE: COMPLETE/PARTIAL/FAILED
FIRESTORE: COMPLETE/PARTIAL/FAILED
CLOUDINARY: COMPLETE/PARTIAL/FAILED
PDF EXTRACTION: COMPLETE/PARTIAL/FAILED
IMAGE OCR: COMPLETE/PARTIAL/FAILED
LOCAL LLM: COMPLETE/PARTIAL/FAILED
GITHUB: COMPLETE/PARTIAL/FAILED
SCRAPLING: COMPLETE/PARTIAL/FAILED
RECRUITER PORTAL: COMPLETE/PARTIAL/FAILED
JOB SEEKER PORTAL: COMPLETE/PARTIAL/FAILED
AI INVESTIGATION UI: COMPLETE/PARTIAL/FAILED
EVIDENCE GRAPH: COMPLETE/PARTIAL/FAILED

END-TO-END DEMO
Recruiter → Create → Publish
Candidate → View → Apply → Upload
AI → Ingest → Structure → Investigate → Assess
Recruiter → Review → Compare → Shortlist

BLOCKERS / LIMITATIONS
List only actual blockers.
```

# FINAL CLAUDE COMMAND

**Build the complete EvidenceHire system now.**

Do not treat this document as a UI mockup request. Implement the actual backend, frontend, authentication, persistence, storage, document ingestion, OCR, local LLM investigation, evidence verification, external evidence integration, assessment engine integration, and presentation flow.

First audit the existing repository and produce a short gap report. Then implement the phases in order. Reuse the existing Challenge 01 and Challenge 02 engine. Do not remove working behavior.

Most importantly, do not stop when code exists. **Run the system. Test the system. Verify the real end-to-end flow.**

The final product must make the following chain obvious:

```text
Candidate Claim
      ↓
Evidence Search
      ↓
Actual Evidence
      ↓
Evidence Level
      ↓
Requirement Assessment
      ↓
WHY?
      ↓
Explainable Result
```

The previous evaluator should be able to ask:

> "Why did you accept this?"

and the product should answer visually.

They should ask:

> "Why didn't you map ECS directly to container orchestration?"

and the product should show:

```text
RELATED — NOT AUTOMATICALLY EQUIVALENT
```

They should ask:

> "What happens when Junior and 5+ years conflict?"

and the product should show:

```text
REQUISITION CONFLICT
RECRUITER REVIEW REQUIRED
```

They should ask:

> "What evidence supports this candidate?"

and the product should show the source, evidence level, confidence, and WHY explanation.

**Build the product around evidence, not around a score.**
