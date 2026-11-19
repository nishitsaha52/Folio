import { ArrowDownToLine, Network } from "lucide-react";
import type { Artifact } from "../../types";
import type { DownloadUrl } from "./types";
export function DiagramsTab({
  artifacts,
  download,
}: {
  artifacts: Artifact[];
  download: DownloadUrl;
}) {
  return (
    <div className="diagram-grid">
      {artifacts
        .filter((a) => a.path.endsWith(".svg"))
        .map((a) => (
          <section className="panel" key={a.path}>
            <div className="panel-heading">
              <Network size={18} />
              <h2>
                {a.path
                  .split("/")
                  .pop()
                  ?.replace(".svg", "")
                  .replaceAll("_", " ")}
              </h2>
              <a href={download(a.path)} aria-label="Download diagram">
                <ArrowDownToLine size={17} />
              </a>
            </div>
            <img src={download(a.path)} alt={a.path.split("/").pop()} />
            <p className="form-note">
              Connections are labelled by observed evidence. Inferred actors and
              incomplete data flows require review.
            </p>
          </section>
        ))}
    </div>
  );
}
