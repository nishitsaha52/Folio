import type { ReactNode } from "react";
import { Search } from "lucide-react";
export interface RecordControls {
  query: string;
  recordPage: number;
  onQueryChange: (query: string) => void;
  onPageChange: (page: number) => void;
}
export function RecordsPanel({
  tab,
  recordCount,
  query,
  recordPage,
  onQueryChange,
  onPageChange,
  children,
}: RecordControls & {
  tab: "requirements" | "tests";
  recordCount: number;
  children: ReactNode;
}) {
  const pageStart = recordPage * 100;
  return (
    <>
      <div className="results-toolbar">
        <div className="input-icon">
          <Search size={17} />
          <input
            placeholder={`Search ${tab}, IDs or modules…`}
            value={query}
            onChange={(e) => {
              onQueryChange(e.target.value);
            }}
            aria-label={`Search ${tab}`}
          />
        </div>
        <span className="muted">{recordCount} records</span>
      </div>
      {children}
      {recordCount > 100 && (
        <nav className="results-toolbar" aria-label="Record pages">
          <button
            className="secondary"
            disabled={recordPage === 0}
            onClick={() => onPageChange(recordPage - 1)}
          >
            Previous page
          </button>
          <span>
            Showing {pageStart + 1}–{Math.min(pageStart + 100, recordCount)} of{" "}
            {recordCount}
          </span>
          <button
            className="secondary"
            disabled={pageStart + 100 >= recordCount}
            onClick={() => onPageChange(recordPage + 1)}
          >
            Next page
          </button>
        </nav>
      )}
    </>
  );
}
