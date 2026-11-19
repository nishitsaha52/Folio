import { useEffect, useState } from "react";
import { LockKeyhole } from "lucide-react";
import type { Job } from "../types";
import { api, post } from "../api";

export function AccessPanel({
  job,
  connected,
  onError,
}: {
  job: Job;
  connected: boolean;
  onError: (message: string) => void;
}) {
  const [members, setMembers] = useState<{ login: string; role: string }[]>([]);
  const [login, setLogin] = useState("");
  const [role, setRole] = useState("viewer");
  const [ack, setAck] = useState(false);
  const [saving, setSaving] = useState(false);
  const refresh = () =>
    api<typeof members>(`/jobs/${job.id}/collaborators`).then(setMembers);
  useEffect(() => {
    refresh().catch((e) => onError(e.message));
  }, [job.id]);
  return (
    <section className="panel">
      <div className="panel-heading">
        <LockKeyhole size={20} />
        <h2>Collaborator access</h2>
      </div>
      <p className="muted">
        Grant access to this analysis, its source evidence and all artifact
        versions. Reviewer access also requires the server's authorized reviewer
        list. Access is resolved to the verified GitHub account ID.
      </p>
      {!connected && (
        <div className="notice">
          Connect your GitHub account before sharing an analysis.
        </div>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          try {
            await post(`/jobs/${job.id}/collaborators`, {
              login,
              role,
              acknowledged: ack,
            });
            await refresh();
            setLogin("");
            setAck(false);
          } catch (e) {
            onError((e as Error).message);
          } finally {
            setSaving(false);
          }
        }}
      >
        <div className="form-columns">
          <label>
            GitHub username
            <input
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              pattern="[A-Za-z0-9][A-Za-z0-9-]{0,38}"
              required
            />
          </label>
          <label>
            Role
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="viewer">View documents and evidence</option>
              <option value="reviewer">Review and record evidence</option>
            </select>
          </label>
        </div>
        <label className="checkbox-note">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            required
          />
          <span>
            I authorize sharing all documentation and source evidence in this
            analysis with this GitHub account.
          </span>
        </label>
        <button className="primary" disabled={saving || !connected}>
          {saving ? "Saving…" : "Grant access"}
        </button>
      </form>
      <div className="summary-divider" />
      {members.length ? (
        members.map((member) => (
          <div className="summary-row" key={member.login}>
            <span>
              {member.login} · {member.role}
            </span>
            <button
              className="text-button"
              onClick={async () => {
                try {
                  await api(`/jobs/${job.id}/collaborators/${member.login}`, {
                    method: "DELETE",
                  });
                  await refresh();
                } catch (e) {
                  onError((e as Error).message);
                }
              }}
            >
              Revoke access
            </button>
          </div>
        ))
      ) : (
        <p className="form-note">
          Only the analysis owner currently has access.
        </p>
      )}
    </section>
  );
}
