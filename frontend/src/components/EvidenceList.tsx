import { ChevronDown, Code2 } from "lucide-react";
import type { Evidence } from "../types";
import { Badge } from "./shared";

export function EvidenceList({
  ids,
  evidence,
}: {
  ids: string[];
  evidence: Map<string, Evidence>;
}) {
  return (
    <details className="evidence-details">
      <summary>
        <Code2 size={14} /> Source evidence <Badge>{ids.length}</Badge>
        <ChevronDown size={13} />
      </summary>
      {ids.map((id) => {
        const e = evidence.get(id);
        return e ? (
          <div key={id}>
            <p>
              <code>{e.id}</code> · {e.path}:{e.start_line}–{e.end_line}
            </p>
            <pre className="code-block">{e.snippet}</pre>
          </div>
        ) : null;
      })}
    </details>
  );
}
