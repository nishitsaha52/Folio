import { ArrowLeft, CircleHelp, Sparkles } from "lucide-react";
import type { Job } from "../../types";
export function AnalysisProgress({
  job,
  onBack,
}: {
  job: Job;
  onBack: () => void;
}) {
  return (
    <div>
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={16} /> Workspace
      </button>
      <div className="progress-card">
        <span className="progress-icon">
          {job.status === "failed" ? (
            <CircleHelp size={32} />
          ) : (
            <Sparkles size={32} />
          )}
        </span>
        <div className="eyebrow">{job.repository}</div>
        <h1>
          {job.status === "failed"
            ? "Analysis needs attention"
            : "Reading between the lines."}
        </h1>
        <p>{job.message}</p>
        <p className="form-note" aria-live="polite">
          {job.diagnostics?.stage}
          {job.diagnostics?.backend && " · " + job.diagnostics.backend}
          {job.updated &&
            " · Last update " +
              new Date(
                job.updated + (job.updated.endsWith("Z") ? "" : "Z"),
              ).toLocaleTimeString()}
        </p>
        {job.status === "queued" && job.diagnostics?.backend === "celery" && (
          <p className="form-note">
            Waiting for a Celery worker to claim this analysis. The API can be
            healthy while no worker is running.
          </p>
        )}
        <div className="progress-track">
          <span style={{ width: `${job.progress}%` }} />
        </div>
        <div className="progress-label">
          <span>
            {job.status === "failed" ? "Stopped" : "Analysis in progress"}
          </span>
          <strong>{job.progress}%</strong>
        </div>
        <p className="form-note">
          Source retrieval → static evidence → requirements → documentation
        </p>
        {job.diagnostics?.latest_failure && job.status === "failed" && (
          <section className="job-diagnostics" aria-label="Failure details">
            <h2>Why the analysis stopped</h2>
            <p>{job.diagnostics.latest_failure.message}</p>
            {job.diagnostics.latest_failure.last_message && (
              <p>
                Last checkpoint: {job.diagnostics.latest_failure.last_message}
              </p>
            )}
            {job.diagnostics.latest_failure.error_type && (
              <p className="form-note">
                Error type: {job.diagnostics.latest_failure.error_type}
              </p>
            )}
          </section>
        )}
        {!!job.diagnostics?.history.length && (
          <details className="job-diagnostics">
            <summary>Execution history</summary>
            <ol>
              {job.diagnostics.history.map((event, index) => (
                <li key={event.created + "-" + index}>
                  <strong>
                    {event.stage || event.action.replaceAll("_", " ")}
                  </strong>
                  {event.stage_progress !== undefined &&
                    " · " + event.stage_progress + "%"}
                  {event.backend && " · " + event.backend}
                  <p>{event.message || event.last_message}</p>
                  {event.last_message &&
                    event.last_message !== event.message && (
                      <p className="form-note">
                        Previous checkpoint: {event.last_message}
                      </p>
                    )}
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
    </div>
  );
}
