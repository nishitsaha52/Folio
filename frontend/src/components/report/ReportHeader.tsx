import {
  ArrowDownToLine,
  ArrowLeft,
  CheckCheck,
  GitBranch,
  ShieldCheck,
} from "lucide-react";
import type { Analysis, Job, Workflow } from "../../types";
import type { DownloadUrl, ReportTab } from "./types";
import { Badge, human } from "../shared";
export function ReportHeader({
  job,
  analysis,
  state,
  tab,
  onTabChange,
  onReview,
  onBack,
  download,
}: {
  job: Job;
  analysis: Analysis;
  state: Workflow;
  tab: ReportTab;
  onTabChange: (tab: ReportTab) => void;
  onReview: () => void;
  onBack: () => void;
  download: DownloadUrl;
}) {
  const tabs: ReportTab[] = [
    "overview",
    "requirements",
    "tests",
    "documents",
    "diagrams",
    "activity",
  ];
  if (job.is_owner) tabs.push("access");
  return (
    <>
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={16} /> Workspace
      </button>
      <div className="report-heading">
        <div>
          <div className="eyebrow">DOCUMENTATION WORKSPACE</div>
          <h1>{job.repository.split("/")[1]}</h1>
          <div className="report-meta">
            <span>{job.repository}</span>
            <span>
              <GitBranch size={13} /> {analysis.commit.slice(0, 10)}
            </span>
            <Badge>Version {job.version}</Badge>
          </div>
        </div>
        <div className="report-actions">
          <button className="secondary" onClick={onReview}>
            <CheckCheck size={16} /> Review baseline
          </button>
          <a className="primary" href={download()}>
            <ArrowDownToLine size={16} /> Download package
          </a>
        </div>
      </div>
      <div className="review-strip">
        <ShieldCheck size={17} />
        <span>
          Requirements{" "}
          <Badge
            tone={state.requirements_status === "approved" ? "green" : "amber"}
          >
            {human(state.requirements_status)}
          </Badge>
        </span>
        <span>
          Application acceptance{" "}
          <Badge tone={state.uat_status === "approved" ? "green" : "amber"}>
            {human(state.uat_status)}
          </Badge>
        </span>
        <small>Approvals are controlled by authorized reviewers.</small>
      </div>
      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <button
            role="tab"
            aria-selected={tab === t}
            className={tab === t ? "active" : ""}
            key={t}
            onClick={() => {
              onTabChange(t);
            }}
          >
            {t}
            {t === "requirements" && (
              <span>{analysis.requirements.length}</span>
            )}
            {t === "tests" && <span>{analysis.test_cases.length}</span>}
          </button>
        ))}
      </div>
    </>
  );
}
