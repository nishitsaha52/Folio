import { useState } from "react";
import { ArrowDownToLine, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../../api";
import type { Artifact, Job } from "../../types";
import type { DownloadUrl } from "./types";
import { Modal } from "../Modal";
export function DocumentsTab({
  job,
  artifacts,
  download,
  onError,
}: {
  job: Job;
  artifacts: Artifact[];
  download: DownloadUrl;
  onError: (message: string) => void;
}) {
  const [preview, setPreview] = useState<{ name: string; text: string } | null>(
    null,
  );
  return (
    <>
      <div className="section-heading">
        <div>
          <h2>Your documentation package</h2>
          <p>Preview Markdown or download individual artifacts.</p>
        </div>
        <select
          aria-label="Download earlier version"
          defaultValue=""
          onChange={(e) => {
            if (e.target.value)
              window.location.href = download("", Number(e.target.value));
          }}
        >
          <option value="">Version history</option>
          {[...(job.versions || [job.version])].reverse().map((v) => (
            <option key={v} value={v}>
              Download version {v}
            </option>
          ))}
        </select>
      </div>
      <div className="artifact-list">
        {artifacts.map((file) => (
          <div key={file.path}>
            <span className="file-icon">
              <FileText size={20} />
            </span>
            <div>
              <strong>
                {file.path.split("/").pop()?.replaceAll("_", " ")}
              </strong>
              <small>
                {file.path.split("/")[0]} · {(file.bytes / 1024).toFixed(1)} KB
              </small>
            </div>
            {file.path.endsWith(".md") && (
              <button
                className="text-button"
                onClick={async () => {
                  try {
                    const r = await api<{ content: string }>(
                      `/jobs/${job.id}/preview?path=${encodeURIComponent(file.path)}`,
                    );
                    setPreview({
                      name: file.path.split("/").pop()!,
                      text: r.content,
                    });
                  } catch (e) {
                    onError((e as Error).message);
                  }
                }}
              >
                Preview
              </button>
            )}
            <a
              className="icon-button"
              href={download(file.path)}
              aria-label={`Download ${file.path}`}
            >
              <ArrowDownToLine size={17} />
            </a>
          </div>
        ))}
      </div>
      {preview && (
        <Modal
          wide
          title={preview.name.replaceAll("_", " ")}
          onClose={() => setPreview(null)}
        >
          <div className="markdown-preview">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {preview.text}
            </ReactMarkdown>
          </div>
        </Modal>
      )}
    </>
  );
}
