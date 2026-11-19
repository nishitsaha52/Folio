import { useMemo } from "react";
import { FileCode2 } from "lucide-react";
import type { Evidence, Requirement } from "../../types";
import { Badge } from "../shared";
import { EvidenceList } from "../EvidenceList";
import { RecordsPanel, type RecordControls } from "./RecordsPanel";
export function RequirementsTab({
  requirements,
  sourceEvidence,
  canReview,
  onEdit,
  ...controls
}: RecordControls & {
  requirements: Requirement[];
  sourceEvidence: Evidence[];
  canReview: boolean;
  onEdit: (requirement: Requirement) => void;
}) {
  const evidence = useMemo(
    () => new Map(sourceEvidence.map((item) => [item.id, item])),
    [sourceEvidence],
  );
  const matchingRequirements = requirements.filter((r) =>
    `${r.id} ${r.title} ${r.module}`
      .toLowerCase()
      .includes(controls.query.toLowerCase()),
  );
  const pageStart = controls.recordPage * 100;
  return (
    <RecordsPanel
      tab="requirements"
      recordCount={matchingRequirements.length}
      {...controls}
    >
      {matchingRequirements.slice(pageStart, pageStart + 100).map((r) => (
        <article className="requirement-card" key={r.id}>
          <div className="record-heading">
            <code>{r.id}</code>
            <Badge tone="amber">{r.confidence}</Badge>
            {canReview && (
              <button className="text-button" onClick={() => onEdit(r)}>
                Edit requirement
              </button>
            )}
          </div>
          <h3>{r.title}</h3>
          <p>{r.statement}</p>
          <div className="record-meta">
            <FileCode2 size={14} /> {r.module}
            <span>Source: {r.source}</span>
          </div>
          <EvidenceList ids={r.evidence_ids} evidence={evidence} />
        </article>
      ))}
    </RecordsPanel>
  );
}
