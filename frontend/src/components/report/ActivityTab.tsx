import { CheckCheck } from "lucide-react";
import type { AuditEntry, Workflow } from "../../types";
import { Badge, human, time } from "../shared";
export function ActivityTab({
  audit,
  state,
}: {
  audit: AuditEntry[];
  state: Workflow;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <CheckCheck size={20} />
        <h2>Version and review history</h2>
      </div>
      {audit.map((a) => (
        <div className="audit-row" key={a.id}>
          <span className="audit-dot" />
          <div>
            <strong>{human(a.action)}</strong>
            <p>
              {a.actor} · {time(a.created)}
            </p>
            <code>{JSON.stringify(a.detail)}</code>
          </div>
        </div>
      ))}
      {state.reviews.map((r) => (
        <div className="review-comment" key={r.id}>
          <Badge>{r.current ? "Current baseline" : "Earlier baseline"}</Badge>
          <strong>
            {r.reviewer}: {human(r.decision)}
          </strong>
          <p>{r.comment}</p>
        </div>
      ))}
    </section>
  );
}
