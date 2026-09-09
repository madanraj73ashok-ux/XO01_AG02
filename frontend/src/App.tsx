// The application shell: landing, sign-in, and the two portals.
//
// Which portal a person sees is decided by the role the server holds for them,
// never by the client. The footer reports which backends are actually live, so
// a demo running on local storage says so rather than implying otherwise.

import { useState } from "react";
import type { ReactNode } from "react";
import {
  BrowserRouter,
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { AuthProvider, useAuth } from "./product/auth";
import type { Role } from "./product/api";
import Recruiter from "./product/Recruiter";
import Seeker from "./product/Seeker";
import LegacyConsole from "./LegacyConsole";

const TAGLINE =
  "Don't just read what candidates claim. Verify what the evidence supports.";

// --------------------------------------------------------------------------
// Landing
// --------------------------------------------------------------------------

function Landing() {
  const navigate = useNavigate();
  const { signIn, config, usesFirebase } = useAuth();
  const [role, setRole] = useState<Role | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const complete =
    Boolean(role) &&
    name.trim().length > 0 &&
    (!usesFirebase || (email.trim().length > 0 && password.length >= 6));

  async function enter(event: React.FormEvent) {
    event.preventDefault();
    if (!role || !complete) return;
    setBusy(true);
    setError("");
    try {
      const session = await signIn({
        name: name.trim(),
        role,
        email: email.trim(),
        password,
      });
      navigate(session.role === "RECRUITER" ? "/recruiter" : "/jobs");
    } catch (problem) {
      setError((problem as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-6 py-16">
      <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-accent">
        EvidenceHire
      </p>
      <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight text-white sm:text-5xl">
        {TAGLINE}
      </h1>
      <p className="mt-5 max-w-2xl text-base leading-relaxed text-slate-300">
        Every skill claim is separated from the evidence behind it, graded on an
        E0&ndash;E4 ladder, and reported with the reasoning attached. A claim and
        its evidence are never conflated, and missing evidence is never treated
        as proof of absence.
      </p>

      <form onSubmit={enter} className="mt-10 max-w-xl space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          {(
            [
              ["RECRUITER", "I'm a Recruiter", "Publish roles, review evidence"],
              ["JOB_SEEKER", "I'm a Job Seeker", "Apply and see why"],
            ] as [Role, string, string][]
          ).map(([value, label, hint]) => (
            <button
              key={value}
              type="button"
              onClick={() => setRole(value)}
              className={`rounded-xl border p-5 text-left transition ${
                role === value
                  ? "border-accent bg-accent/10"
                  : "border-white/15 bg-panel/40 hover:border-accent/50"
              }`}
            >
              <p className="text-base font-semibold text-white">{label}</p>
              <p className="mt-1 text-xs text-soft">{hint}</p>
            </button>
          ))}
        </div>

        {role ? (
          <>
            <label className="block">
              <span className="eyebrow">Your name</span>
              <input
                autoFocus
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Anita Rao"
                className="mt-1 w-full rounded border border-white/15 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-accent"
              />
            </label>

            {usesFirebase ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="eyebrow">Email</span>
                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                    className="mt-1 w-full rounded border border-white/15 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-accent"
                  />
                </label>
                <label className="block">
                  <span className="eyebrow">Password (6+ characters)</span>
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="at least six characters"
                    className="mt-1 w-full rounded border border-white/15 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-accent"
                  />
                </label>
              </div>
            ) : null}

            {error ? <p className="text-xs text-rose-300">{error}</p> : null}

            <button
              type="submit"
              disabled={busy || !complete}
              className="rounded bg-accent px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-accent/90 disabled:opacity-40"
            >
              {busy ? "Signing in..." : "Continue"}
            </button>

            {config?.authIsVerified ? (
              <p className="text-[11px] leading-relaxed text-soft">
                Signing in against Firebase project{" "}
                <span className="font-mono">evidencehire-1247</span>. An account
                is created on first use. The server verifies the ID token before
                it will answer anything.
              </p>
            ) : (
              <p className="text-[11px] leading-relaxed text-soft">
                Signing in with a development identity. Firebase is not
                configured on this server, so this session is not
                identity-verified &mdash; the interface says so wherever it
                matters.
              </p>
            )}
          </>
        ) : null}
      </form>

      <p className="mt-12 text-xs text-soft">
        <Link to="/console" className="text-accent hover:underline">
          Open the offline 12-candidate demo pool
        </Link>{" "}
        &mdash; the deterministic evaluation set, no sign-in needed.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------
// Shell
// --------------------------------------------------------------------------

function Shell({ children }: { children: ReactNode }) {
  const { session, config, signOut } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const links: [string, string][] =
    session?.role === "RECRUITER"
      ? [
          ["/recruiter", "Requisitions"],
          ["/recruiter/new", "Create job"],
          ["/console", "Demo pool"],
        ]
      : [
          ["/jobs", "Open roles"],
          ["/applications", "My applications"],
          ["/console", "Demo pool"],
        ];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-white/10 bg-ink/60">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-4 px-6 py-3">
          <Link to="/" className="font-mono text-sm font-semibold text-accent">
            EvidenceHire
          </Link>

          <nav className="flex flex-wrap gap-1">
            {links.map(([to, label]) => (
              <Link
                key={to}
                to={to}
                className={`rounded px-3 py-1.5 text-sm transition ${
                  location.pathname === to
                    ? "bg-accent/15 font-medium text-accent"
                    : "text-slate-300 hover:bg-white/5"
                }`}
              >
                {label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {session ? (
              <>
                <span className="text-xs text-soft">
                  {session.name} &middot;{" "}
                  {session.role === "RECRUITER" ? "Recruiter" : "Job seeker"}
                </span>
                <button
                  onClick={() => {
                    signOut();
                    navigate("/");
                  }}
                  className="rounded border border-white/15 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-slate-300 transition hover:border-accent/50 hover:text-accent"
                >
                  sign out
                </button>
              </>
            ) : (
              <Link
                to="/"
                className="rounded border border-white/15 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-slate-300"
              >
                sign in
              </Link>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-6 py-7">{children}</main>

      <footer className="border-t border-white/10 px-6 py-3">
        <div className="mx-auto flex max-w-[1400px] flex-wrap gap-x-5 gap-y-1 font-mono text-[10px] uppercase tracking-wider text-soft">
          <span>
            auth: {config?.authMode ?? "unknown"}
            {config && !config.authIsVerified ? " (not verified)" : ""}
          </span>
          <span>records: {config?.storeBackend ?? "unknown"}</span>
          <span>documents: {config?.fileBackend ?? "unknown"}</span>
          <span className="ml-auto normal-case tracking-normal">
            A human makes the hiring decision.
          </span>
        </div>
      </footer>
    </div>
  );
}

function Protected({ role, children }: { role: Role; children: ReactNode }) {
  const { session, ready } = useAuth();
  if (!ready) return <p className="p-6 text-sm text-soft">Loading session...</p>;
  if (!session) return <Navigate to="/" replace />;
  if (session.role !== role) {
    return (
      <Navigate to={session.role === "RECRUITER" ? "/recruiter" : "/jobs"} replace />
    );
  }
  return <Shell>{children}</Shell>;
}

function Root() {
  const { session, ready } = useAuth();
  if (!ready) return <p className="p-6 text-sm text-soft">Loading...</p>;
  if (session) {
    return (
      <Navigate to={session.role === "RECRUITER" ? "/recruiter" : "/jobs"} replace />
    );
  }
  return <Landing />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Root />} />
          <Route
            path="/console"
            element={
              <Shell>
                <LegacyConsole />
              </Shell>
            }
          />
          <Route
            path="/recruiter/*"
            element={
              <Protected role="RECRUITER">
                <Recruiter />
              </Protected>
            }
          />
          {/* The seeker portal owns several top-level paths (/jobs and
              /applications), so it is mounted once at the root rather than
              twice - a component mounted at two prefixes cannot resolve its
              own relative child routes. */}
          <Route
            path="/*"
            element={
              <Protected role="JOB_SEEKER">
                <Seeker />
              </Protected>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
