import {
  ArrowRight,
  Check,
  FileText,
  FolderGit2,
  Layers3,
  LockKeyhole,
  Plus,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { Session } from "../../types";

export function WorkspaceIntro({
  repositoryCount,
  completed,
  busy,
  session,
  onDemo,
}: {
  repositoryCount: number;
  completed: number;
  busy: boolean;
  session: Session | null;
  onDemo: () => void;
}) {
  return (
    <>
      <section className="hero">
        <div>
          <div className="eyebrow">
            <span /> FROM SOURCE TO SHARED UNDERSTANDING
          </div>
          <h1>
            Your codebase.
            <br />
            <em>Clearly documented.</em>
          </h1>
          <p>
            Turn a repository into requirements, architecture, and test
            documentation. Grounded in code. Ready for human review.
          </p>
          <div className="hero-actions">
            <button
              className="primary"
              onClick={() =>
                document.getElementById("repository-input")?.focus()
              }
            >
              <Plus size={17} /> Start an analysis
            </button>
            <button
              className="text-button"
              disabled={busy || !session}
              onClick={onDemo}
            >
              Explore the demo <ArrowRight size={16} />
            </button>
          </div>
        </div>
        <div className="hero-illustration" aria-hidden="true">
          <div className="source-card">
            <FolderGit2 size={23} />
            <div>
              <strong>Repository</strong>
              <span>Code · configuration · tests</span>
            </div>
            <div className="code-line" />
            <div className="code-line short" />
          </div>
          <div className="connector">
            <span />
            <Sparkles size={19} />
            <span />
          </div>
          <div className="document-stack">
            <div className="stack-back" />
            <div className="document-card">
              <span className="doc-label">DOCUMENTATION PACKAGE</span>
              <div>
                <FileText size={18} />
                <strong>Requirements</strong>
                <Check size={15} />
              </div>
              <div>
                <Layers3 size={18} />
                <strong>Architecture</strong>
                <Check size={15} />
              </div>
              <div>
                <ShieldCheck size={18} />
                <strong>Test scenarios</strong>
                <Check size={15} />
              </div>
              <span className="evidence-chip">Linked to source evidence</span>
            </div>
          </div>
        </div>
      </section>
      <div className="overview-stats">
        <div>
          <span className="stat-icon">
            <FolderGit2 size={20} />
          </span>
          <div>
            <strong>{repositoryCount}</strong>
            <span>Accessible repositories</span>
          </div>
        </div>
        <div>
          <span className="stat-icon">
            <FileText size={20} />
          </span>
          <div>
            <strong>{completed}</strong>
            <span>Completed analyses</span>
          </div>
        </div>
        <div>
          <span className="stat-icon">
            <Layers3 size={20} />
          </span>
          <div>
            <strong>7</strong>
            <span>Documentation deliverables</span>
          </div>
        </div>
        <div>
          <span className="stat-icon">
            <LockKeyhole size={20} />
          </span>
          <div>
            <strong>Read only</strong>
            <span>Source access by default</span>
          </div>
        </div>
      </div>
    </>
  );
}
