import { CircleHelp, Layers3, Sparkles } from "lucide-react";
import type { Analysis, Workflow } from "../../types";
export function OverviewTab({
  analysis,
  state,
}: {
  analysis: Analysis;
  state: Workflow;
}) {
  return (
    <>
      <div className="report-stats">
        {[
          [analysis.stats.scanned_files, "Files inspected"],
          [analysis.requirements.length, "Requirement candidates"],
          [state.counts.unexecuted, "Unexecuted test cases"],
          [analysis.stats.reused_files, "Files reused from cache"],
        ].map(([value, caption]) => (
          <div key={caption}>
            <strong>{value}</strong>
            <span>{caption}</span>
          </div>
        ))}
      </div>
      {analysis.scope && (
        <section className="panel scan-coverage" aria-label="Scan coverage">
          <h2>
            {analysis.scope.partial
              ? "Documentation has coverage gaps"
              : "Scan coverage"}
          </h2>
          <p>
            {analysis.scope.skipped_files.length} paths could not be inspected ·{" "}
            {analysis.scope.auto_exclusions.length} generated or dependency
            paths automatically excluded.
          </p>
          {analysis.scope.budget_reached && (
            <p>
              The analysis budget was reached. Increase analysis depth or refine
              your ignore rules to inspect more source files.
            </p>
          )}
          {analysis.scope.skipped_files.length > 0 && (
            <details open>
              <summary>Skipped paths</summary>
              <ul>
                {analysis.scope.skipped_files
                  .slice(0, 20)
                  .map((item, index) => (
                    <li key={item.path + "-" + index}>
                      <code>{item.path}</code> — {item.message}{" "}
                      {item.code !== null && "(OS code " + item.code + ")"}
                    </li>
                  ))}
              </ul>
              <p className="form-note">
                Full details are included in 06-analysis/Scope_Report.md and
                Scope_Report.json.
              </p>
            </details>
          )}
          {analysis.scope.auto_exclusions.length > 0 && (
            <details>
              <summary>Automatically excluded paths and reasons</summary>
              <ul>
                {analysis.scope.auto_exclusions
                  .slice(0, 20)
                  .map((item, index) => (
                    <li key={item.path + "-" + index}>
                      <code>{item.path}</code> — {item.reason}
                    </li>
                  ))}
              </ul>
            </details>
          )}
          <p className="form-note">
            Up to 20 paths per list are shown here. The complete coverage report
            is included in 06-analysis/Scope_Report.md and Scope_Report.json.
          </p>
          {!!analysis.scope.suggested_ignore_patterns.length && (
            <details>
              <summary>Suggested .docagentignore rules</summary>
              <p>
                Review these rules before adding them to your repository. Prefix
                a file rule with ! to include an automatically detected
                generated file.
              </p>
              <pre className="code-block">
                {analysis.scope.suggested_ignore_patterns.join("\n")}
              </pre>
            </details>
          )}
        </section>
      )}
      <div className="report-columns">
        <section className="panel">
          <div className="panel-heading">
            <Layers3 size={19} />
            <h2>Detected technologies</h2>
          </div>
          <div className="tech-tags">
            {[
              ...new Set(
                analysis.findings
                  .filter((f) => f.kind === "technology")
                  .map((f) => f.title),
              ),
            ].map((t) => (
              <span key={t}>{t}</span>
            ))}
          </div>
          <div className="summary-divider" />
          <h3>Repository composition</h3>
          {Object.entries(analysis.stats.languages).map(([language, count]) => (
            <div className="language-row" key={language}>
              <span>{language}</span>
              <div>
                <span
                  style={{
                    width: `${(count / analysis.stats.scanned_files) * 100}%`,
                  }}
                />
              </div>
              <strong>{count}</strong>
            </div>
          ))}
          {analysis.changes && (
            <>
              <div className="summary-divider" />
              <h3>
                Changes since {analysis.changes.previous_commit.slice(0, 8)}
              </h3>
              <p className="muted">
                {analysis.changes.added.length} added ·{" "}
                {analysis.changes.modified.length} modified ·{" "}
                {analysis.changes.removed.length} removed
              </p>
            </>
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <CircleHelp size={19} />
            <h2>Items for human review</h2>
          </div>
          <p className="muted">
            These limits and clarifications are included in your documentation.
          </p>
          <div className="gaps-list">
            {analysis.gaps.map((gap, i) => (
              <p key={i}>
                <span>{String(i + 1).padStart(2, "0")}</span>
                {gap}
              </p>
            ))}
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <Sparkles size={19} />
          <h2>AI usage & execution evidence</h2>
        </div>
        {analysis.usage.length ? (
          <p>
            {analysis.usage.filter((u) => u.status === "completed").length}{" "}
            successful requests ·{" "}
            {analysis.usage
              .reduce(
                (s, u) => s + (u.input_tokens || 0) + (u.output_tokens || 0),
                0,
              )
              .toLocaleString()}{" "}
            reported tokens. Failed-request usage may be unavailable.
          </p>
        ) : (
          <p className="muted">
            Static analysis only. No repository evidence was sent to an AI
            provider.
          </p>
        )}
        {analysis.execution ? (
          <pre className="code-block">
            {JSON.stringify(analysis.execution, null, 2)}
          </pre>
        ) : (
          <p className="form-note">
            Repository tests were not executed. Generated test cases remain
            unexecuted until verified results are recorded.
          </p>
        )}
      </section>
    </>
  );
}
