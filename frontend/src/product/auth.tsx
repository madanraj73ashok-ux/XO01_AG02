// Session state for the two-sided product.
//
// The server decides how a caller is authenticated and reports it through
// /api/config. When Firebase is live the browser signs in against it for real
// and forwards the resulting ID token, which the server verifies. When it is
// not, a clearly-labelled development identity is used instead - and the
// interface says which of the two is in force rather than implying the
// stronger one.
//
// ID tokens expire after an hour, so the stored token is refreshed from
// `onIdTokenChanged` rather than captured once at sign-in.

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  createUserWithEmailAndPassword,
  onIdTokenChanged,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
  updateProfile,
} from "firebase/auth";
import { api, readToken, writeToken } from "./api";
import type { Config, Role } from "./api";
import { describeAuthError, firebaseAuth } from "./firebase";

export interface Session {
  uid: string;
  name: string;
  role: Role;
}

export interface Credentials {
  name: string;
  role: Role;
  email?: string;
  password?: string;
}

interface AuthValue {
  session: Session | null;
  config: Config | null;
  ready: boolean;
  error: string;
  usesFirebase: boolean;
  signIn: (credentials: Credentials) => Promise<Session>;
  signOut: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

/** A stable, readable uid from a display name, for development sessions. */
function uidFor(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return slug || "guest";
}

function parseDevToken(token: string): Session | null {
  if (!token.startsWith("dev:")) return null;
  const parts = token.slice(4).split(":");
  if (parts.length < 2) return null;
  const role = parts[1] as Role;
  if (role !== "RECRUITER" && role !== "JOB_SEEKER") return null;
  return { uid: parts[0], role, name: parts[2] ?? parts[0] };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [config, setConfig] = useState<Config | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  const usesFirebase = config?.authMode === "firebase";

  // Load the server's configuration first: it decides which mode applies.
  useEffect(() => {
    let cancelled = false;
    api
      .config()
      .then((current) => {
        if (!cancelled) setConfig(current);
      })
      .catch((problem) => {
        if (cancelled) return;
        setError((problem as Error).message);
        setReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Development mode: restore whatever the stored token claims, then confirm
  // the role with the server.
  useEffect(() => {
    if (config === null || usesFirebase) return;

    const existing = parseDevToken(readToken());
    if (!existing) {
      setReady(true);
      return;
    }

    let cancelled = false;
    api
      .session({
        name: existing.name,
        email: `${existing.uid}@demo.invalid`,
        role: existing.role,
      })
      .then((confirmed) => {
        if (!cancelled) {
          setSession({
            uid: confirmed.uid,
            name: confirmed.name || existing.name,
            role: confirmed.role,
          });
        }
      })
      .catch(() => writeToken(""))
      .finally(() => {
        if (!cancelled) setReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, [config, usesFirebase]);

  // Firebase mode: follow the real auth state, refreshing the stored ID token
  // whenever Firebase rotates it.
  useEffect(() => {
    if (config === null || !usesFirebase) return;

    const unsubscribe = onIdTokenChanged(firebaseAuth(), async (user) => {
      if (!user) {
        writeToken("");
        setSession(null);
        setReady(true);
        return;
      }

      try {
        writeToken(await user.getIdToken());
        const confirmed = await api.session({
          name: user.displayName ?? user.email ?? "",
          email: user.email ?? "",
          // Only consulted when the account is new; a returning user keeps
          // whatever role the server already holds for them.
          role: "JOB_SEEKER",
        });
        setSession({
          uid: confirmed.uid,
          name: confirmed.name || user.displayName || user.email || "",
          role: confirmed.role,
        });
      } catch (problem) {
        setError((problem as Error).message);
      } finally {
        setReady(true);
      }
    });

    return unsubscribe;
  }, [config, usesFirebase]);

  const value = useMemo<AuthValue>(
    () => ({
      session,
      config,
      ready,
      error,
      usesFirebase,

      async signIn({ name, role, email, password }: Credentials) {
        if (usesFirebase) {
          if (!email || !password) {
            throw new Error("Firebase sign-in needs an email and a password.");
          }

          const auth = firebaseAuth();
          let user;
          try {
            ({ user } = await signInWithEmailAndPassword(auth, email, password));
          } catch (problem) {
            const code = (problem as { code?: string }).code ?? "";
            if (code !== "auth/user-not-found" && code !== "auth/invalid-credential") {
              throw new Error(describeAuthError(problem));
            }
            try {
              ({ user } = await createUserWithEmailAndPassword(auth, email, password));
            } catch (signupProblem) {
              throw new Error(describeAuthError(signupProblem));
            }
          }

          if (name && user.displayName !== name) {
            await updateProfile(user, { displayName: name });
          }

          writeToken(await user.getIdToken(true));
          const confirmed = await api.session({ name, email, role });
          const next: Session = {
            uid: confirmed.uid,
            name: confirmed.name || name,
            role: confirmed.role,
          };
          setSession(next);
          return next;
        }

        const uid = uidFor(name);
        writeToken(`dev:${uid}:${role}:${name}`);
        const confirmed = await api.session({
          name,
          email: email || `${uid}@demo.invalid`,
          role,
        });
        const next: Session = {
          uid: confirmed.uid,
          name: confirmed.name || name,
          role: confirmed.role,
        };
        setSession(next);
        writeToken(`dev:${next.uid}:${next.role}:${next.name}`);
        return next;
      },

      signOut() {
        writeToken("");
        setSession(null);
        if (usesFirebase) void firebaseSignOut(firebaseAuth());
      },
    }),
    [session, config, ready, error, usesFirebase]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth used outside AuthProvider");
  return value;
}
