import { useState } from "react";
import type { Case } from "../types";
import { Modal } from "./Modal";

export function ResultModal({
  test,
  baselineHash,
  onClose,
  onSave,
}: {
  test: Case;
  baselineHash: string;
  onClose: () => void;
  onSave: (body: unknown) => Promise<void>;
}) {
  const [status, setStatus] = useState("blocked");
  const [source, setSource] = useState("manual_uat");
  const [actual, setActual] = useState("");
  const [reference, setReference] = useState("");
  const [severity, setSeverity] = useState("none");
  const [attested, setAttested] = useState(false);
  const [saving, setSaving] = useState(false);
  return (
    <Modal title="Record a verified test result" onClose={onClose}>
      <p className="muted">
        {test.id} · {test.title}
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          await onSave({
            test_case_id: test.id,
            status,
            source,
            actual,
            evidence_reference: reference,
            severity,
            attested,
            baseline_hash: baselineHash,
          });
          setSaving(false);
        }}
      >
        <div className="form-columns">
          <label>
            Result
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="blocked">Blocked</option>
              <option value="failed">Failed</option>
              <option value="passed">Passed</option>
            </select>
          </label>
          <label>
            Evidence type
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="manual_uat">Manual UAT</option>
              <option value="existing_report">Verified existing report</option>
            </select>
          </label>
        </div>
        <label>
          Actual outcome
          <textarea
            value={actual}
            onChange={(e) => setActual(e.target.value)}
            minLength={10}
            rows={4}
            required
          />
        </label>
        <label>
          Evidence URL or report reference
          <input
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            minLength={5}
            required
          />
        </label>
        <label>
          Defect severity
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          >
            {["none", "low", "medium", "high", "critical"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="checkbox-note">
          <input
            type="checkbox"
            checked={attested}
            onChange={(e) => setAttested(e.target.checked)}
            required
          />
          <span>
            I verified this evidence against the selected test case and analyzed
            commit.
          </span>
        </label>
        <button className="primary full" disabled={saving}>
          {saving ? "Saving…" : "Record verified result"}
        </button>
      </form>
    </Modal>
  );
}
