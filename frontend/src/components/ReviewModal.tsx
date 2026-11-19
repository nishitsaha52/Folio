import { useState } from "react";
import type { Job } from "../types";
import { Modal } from "./Modal";

export function ReviewModal({
  job,
  canReview,
  onClose,
  onSave,
}: {
  job: Job;
  canReview: boolean;
  onClose: () => void;
  onSave: (body: unknown) => Promise<void>;
}) {
  const [stage, setStage] = useState("requirements");
  const [decision, setDecision] = useState("comment");
  const [comment, setComment] = useState("");
  const [ack, setAck] = useState(false);
  const [saving, setSaving] = useState(false);
  return (
    <Modal title="Record a human review" onClose={onClose}>
      <p className="muted">
        Your decision is bound to the current requirements or UAT evidence
        baseline. Later changes invalidate earlier acceptance.
      </p>
      {!canReview && (
        <div className="notice">
          Sign in with a GitHub account included in the administrator’s reviewer
          list to record decisions.
        </div>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          await onSave({
            stage,
            decision,
            comment,
            acknowledged: ack,
            baseline_hash:
              stage === "requirements"
                ? job.baseline_hash
                : job.workflow?.acceptance_hash,
          });
          setSaving(false);
        }}
      >
        <label>
          Review stage
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="requirements">Requirements baseline</option>
            <option value="uat">Application / UAT acceptance</option>
          </select>
        </label>
        <label>
          Decision
          <select
            value={decision}
            onChange={(e) => setDecision(e.target.value)}
          >
            <option value="comment">Comment only</option>
            <option value="changes_requested">Request changes</option>
            <option
              value="approved"
              disabled={stage === "uat" && !job.workflow?.ready_for_acceptance}
            >
              Approve this baseline
            </option>
          </select>
        </label>
        {stage === "uat" && !job.workflow?.ready_for_acceptance && (
          <p className="form-note">
            Acceptance is pending requirements approval and passing evidence for
            every test case.
          </p>
        )}
        <label>
          Review comment
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            required
            rows={4}
          />
        </label>
        {decision === "approved" && (
          <label className="checkbox-note">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              required
            />
            <span>
              I have reviewed this baseline and am authorized to record this
              approval.
            </span>
          </label>
        )}
        <button
          className="primary full"
          disabled={
            !canReview ||
            saving ||
            (stage === "uat" &&
              decision === "approved" &&
              !job.workflow?.ready_for_acceptance)
          }
        >
          {saving ? "Saving…" : "Record review"}
        </button>
      </form>
    </Modal>
  );
}
