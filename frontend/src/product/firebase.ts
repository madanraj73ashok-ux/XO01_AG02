// Firebase client initialisation.
//
// This configuration is public by design. A Firebase web `apiKey` is a project
// identifier, not a credential - it authorises nothing on its own, and access
// is controlled by Firebase security rules and by the server verifying the ID
// token it receives. The secret half of this integration lives in the
// server's git-ignored .env and never reaches the browser.
//
// Analytics is deliberately not initialised. It has no part in a hiring
// assessment, and loading it would start collecting behavioural data about
// candidates that this product has no business holding.

import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import type { Auth } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyCJDcIiElnvR2tT97i9pn2Pku_A3R2UluE",
  authDomain: "evidencehire-1247.firebaseapp.com",
  projectId: "evidencehire-1247",
  storageBucket: "evidencehire-1247.firebasestorage.app",
  messagingSenderId: "239902291000",
  appId: "1:239902291000:web:9584e8e0edf62bde6e22cd",
  measurementId: "G-72CHQ1PMHG",
};

let auth: Auth | null = null;

/** The Firebase auth instance, created once and only when first needed. */
export function firebaseAuth(): Auth {
  if (auth === null) {
    auth = getAuth(initializeApp(firebaseConfig));
  }
  return auth;
}

export const FIREBASE_PROJECT_ID = firebaseConfig.projectId;

/** Turn a Firebase error code into something a person can act on. */
export function describeAuthError(error: unknown): string {
  const code = (error as { code?: string }).code ?? "";

  switch (code) {
    case "auth/operation-not-allowed":
      return (
        "Email/password sign-in is not enabled on this Firebase project. " +
        "Enable it in the Firebase console under Authentication > Sign-in " +
        "method, then try again."
      );
    case "auth/invalid-credential":
    case "auth/wrong-password":
      return "That email and password do not match an account.";
    case "auth/email-already-in-use":
      return "An account already exists for that email. Try signing in.";
    case "auth/weak-password":
      return "Firebase requires a password of at least six characters.";
    case "auth/invalid-email":
      return "That does not look like an email address.";
    case "auth/network-request-failed":
      return "Could not reach Firebase. Check the network and try again.";
    default:
      return (error as Error).message || "Sign-in failed.";
  }
}
