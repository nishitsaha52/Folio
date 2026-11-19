import { Network } from "lucide-react";
import { DOCS, Badge } from "../shared";
export function WorkspaceFooter() {
  return (
    <>
      <section className="deliverables">
        <div className="section-heading">
          <div>
            <h2>A complete documentation workflow</h2>
            <p>
              From understanding the implementation to recording acceptance.
            </p>
          </div>
          <Badge>MD · DOCX · PDF</Badge>
        </div>
        <div className="deliverable-grid">
          {DOCS.slice(0, 3).map((d, i) => (
            <div key={d.id}>
              <span className="deliverable-number">0{i + 1}</span>
              <d.icon size={22} />
              <h3>{d.title}</h3>
              <p>{d.description}</p>
            </div>
          ))}
          <div>
            <span className="deliverable-number">+4</span>
            <Network size={22} />
            <h3>Architecture & more</h3>
            <p>Data flows, technology stack and acceptance.</p>
          </div>
        </div>
      </section>
      <footer className="page-footer">
        <span>Folio · Repository Documentation Agent</span>
        <span>Traceable by design. Reviewed by people.</span>
      </footer>
    </>
  );
}
