import { useState } from "react";
import type { Requirement } from "../types";
import { Modal } from "./Modal";

export function EditModal({
  requirement,
  onClose,
  onSave,
}: {
  requirement: Requirement;
  onClose: () => void;
  onSave: (s: string, r: string) => Promise<void>;
}) {
  const [statement, setStatement] = useState(requirement.statement);
  const [rationale, setRationale] = useState("");
  const [saving, setSaving] = useState(false);
  return (
    <Modal title={`Edit ${requirement.id}`} onClose={onClose}>
      <p className="muted">
        This creates a new baseline. Earlier approvals and test results remain
        in history and will need revalidation.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          await onSave(statement, rationale);
          setSaving(false);
        }}
      >
        <label>
          Requirement statement
          <textarea
            rows={6}
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            minLength={10}
            required
          />
        </label>
        <label>
          Reason for change
          <textarea
            rows={3}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            minLength={5}
            required
          />
        </label>
        <button className="primary full" disabled={saving}>
          {saving ? "Saving…" : "Save a new baseline"}
        </button>
      </form>
    </Modal>
  );
}
