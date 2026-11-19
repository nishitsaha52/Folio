import { useState } from "react";
import { api } from "../api";
import type { Case, Job, Requirement, Session } from "../types";
import { useReportArtifacts } from "../hooks/useReportArtifacts";
import { AccessPanel } from "./AccessPanel";
import { ReviewModal } from "./ReviewModal";
import { EditModal } from "./EditModal";
import { ResultModal } from "./ResultModal";
import { AnalysisProgress } from "./report/AnalysisProgress";
import { ReportHeader } from "./report/ReportHeader";
import { OverviewTab } from "./report/OverviewTab";
import { RequirementsTab } from "./report/RequirementsTab";
import { TestsTab } from "./report/TestsTab";
import { DocumentsTab } from "./report/DocumentsTab";
import { DiagramsTab } from "./report/DiagramsTab";
import { ActivityTab } from "./report/ActivityTab";
import type { ReportTab } from "./report/types";
export function Report({
  job,
  session,
  onRefresh,
  onError,
  onBack,
}: {
  job: Job;
  session: Session | null;
  onRefresh: () => Promise<void>;
  onError: (message: string) => void;
  onBack: () => void;
}) {
  const [tab, setTab] = useState<ReportTab>("overview");
  const [query, setQuery] = useState("");
  const [recordPage, setRecordPage] = useState(0);
  const [edit, setEdit] = useState<Requirement | null>(null);
  const [test, setTest] = useState<Case | null>(null);
  const [review, setReview] = useState(false);
  const { artifacts, audit } = useReportArtifacts(job, onError);
  const analysis = job.analysis,
    state = job.workflow;
  const download = (path = "", version = job.version) =>
    `/api/jobs/${job.id}/download?${new URLSearchParams({ path, version: String(version) })}`;

  async function mutate(path: string, body: unknown, method = "POST") {
    try {
      await api(`/jobs/${job.id}/${path}`, {
        method,
        body: JSON.stringify(body),
      });
      await onRefresh();
      return true;
    } catch (e) {
      onError((e as Error).message);
      return false;
    }
  }
  if (job.status !== "completed" || !analysis || !state)
    return <AnalysisProgress job={job} onBack={onBack} />;
  const controls = {
    query,
    recordPage,
    onQueryChange: (value: string) => {
      setQuery(value);
      setRecordPage(0);
    },
    onPageChange: setRecordPage,
  };
  return (
    <div className="report">
      <ReportHeader
        job={job}
        analysis={analysis}
        state={state}
        tab={tab}
        download={download}
        onBack={onBack}
        onReview={() => setReview(true)}
        onTabChange={(next) => {
          setTab(next);
          setQuery("");
          setRecordPage(0);
        }}
      />
      {tab === "overview" && <OverviewTab analysis={analysis} state={state} />}
      {tab === "requirements" && (
        <RequirementsTab
          requirements={analysis.requirements}
          sourceEvidence={analysis.evidence}
          canReview={!!job.can_review}
          onEdit={setEdit}
          {...controls}
        />
      )}
      {tab === "tests" && (
        <TestsTab
          cases={analysis.test_cases}
          results={state.results}
          canReview={!!job.can_review}
          onRecord={setTest}
          {...controls}
        />
      )}
      {tab === "documents" && (
        <DocumentsTab
          job={job}
          artifacts={artifacts}
          download={download}
          onError={onError}
        />
      )}
      {tab === "diagrams" && (
        <DiagramsTab artifacts={artifacts} download={download} />
      )}
      {tab === "activity" && <ActivityTab audit={audit} state={state} />}
      {tab === "access" && (
        <AccessPanel job={job} connected={!!session?.login} onError={onError} />
      )}
      {review && (
        <ReviewModal
          job={job}
          canReview={!!job.can_review}
          onClose={() => setReview(false)}
          onSave={async (body) => {
            if (await mutate("reviews", body)) setReview(false);
          }}
        />
      )}
      {edit && (
        <EditModal
          requirement={edit}
          onClose={() => setEdit(null)}
          onSave={async (statement, rationale) => {
            if (
              await mutate(
                `requirements/${edit.id}`,
                { statement, rationale, baseline_hash: job.baseline_hash },
                "PATCH",
              )
            )
              setEdit(null);
          }}
        />
      )}
      {test && (
        <ResultModal
          test={test}
          baselineHash={job.baseline_hash}
          onClose={() => setTest(null)}
          onSave={async (body) => {
            if (await mutate("results", body)) setTest(null);
          }}
        />
      )}
    </div>
  );
}
