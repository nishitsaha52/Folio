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
      </div>
    </div>
  );
}
