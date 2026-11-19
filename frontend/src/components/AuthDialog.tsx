import { Github, LoaderCircle } from "lucide-react";
import type { Session } from "../types";
import { Modal } from "./Modal";
export function AuthDialog({
  session,
  busy,
  token,
  onTokenChange,
  onClose,
  onSubmit,
}: {
  session: Session | null;
  busy: boolean;
  token: string;
  onTokenChange: (token: string) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <Modal title="Connect your GitHub account" onClose={onClose}>
      <p className="muted">
        Use a fine-grained token with read access to repository contents and
        metadata. It is encrypted on the server and never saved in browser
        storage.
      </p>
      {session?.oauth_enabled && (
        <a className="primary full" href="/api/auth/github/start">
          <Github size={18} /> Continue with GitHub OAuth
        </a>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <label>
          Personal access token
          <input
            autoFocus
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => onTokenChange(e.target.value)}
            placeholder="github_pat_…"
            required
          />
        </label>
        <button className="primary full" disabled={busy || !token}>
          {busy ? (
            <LoaderCircle className="spin" size={17} />
          ) : (
            <Github size={17} />
          )}{" "}
          Connect securely
        </button>
      </form>
      <p className="form-note">
        Public repositories can be analyzed without signing in.
      </p>
    </Modal>
  );
}
