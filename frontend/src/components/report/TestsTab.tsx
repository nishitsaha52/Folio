import { ArrowRight, ChevronDown } from "lucide-react";
import type { Case, TestResult } from "../../types";
import { Badge } from "../shared";
import { RecordsPanel, type RecordControls } from "./RecordsPanel";
export function TestsTab({
  cases,
  results,
  canReview,
  onRecord,
  ...controls
}: RecordControls & {
  cases: Case[];
  results: TestResult[];
  canReview: boolean;
  onRecord: (test: Case) => void;
}) {
  const matchingTests = cases.filter((t) =>
    `${t.id} ${t.title} ${t.requirement_id}`
      .toLowerCase()
      .includes(controls.query.toLowerCase()),
  );
  const resultMap = new Map(results.map((r) => [r.test_case_id, r]));
  const pageStart = controls.recordPage * 100;
  return (
    <RecordsPanel tab="tests" recordCount={matchingTests.length} {...controls}>
      {matchingTests.slice(pageStart, pageStart + 100).map((t) => {
        const result = resultMap.get(t.id);
        return (
          <article className="requirement-card" key={t.id}>
            <div className="record-heading">
              <code>{t.id}</code>
              <Badge tone={result?.status === "passed" ? "green" : "amber"}>
                {result?.status || "unexecuted"}
              </Badge>
              <Badge>{t.category}</Badge>
            </div>
            <h3>{t.title}</h3>
            <small className="muted">Requirement {t.requirement_id}</small>
            <details>
              <summary>
                Scenario and expected outcome <ChevronDown size={14} />
              </summary>
              <h4>Preconditions</h4>
              {t.preconditions.map((p) => (
                <p key={p}>{p}</p>
              ))}
              <h4>Steps</h4>
              <ol>
                {t.steps.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ol>
              <h4>Expected result</h4>
              <p>{t.expected}</p>
              {result && (
                <>
                  <h4>Recorded result</h4>
                  <p>{result.actual}</p>
                  <p className="muted">
                    {result.source} · {result.reviewer} ·{" "}
                    {result.evidence_reference}
                  </p>
                </>
              )}
            </details>
            {canReview && (
              <button className="text-button" onClick={() => onRecord(t)}>
                Record verified result <ArrowRight size={14} />
              </button>
            )}
          </article>
        );
      })}
    </RecordsPanel>
  );
}
