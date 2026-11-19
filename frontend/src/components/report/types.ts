export type ReportTab =
  | "overview"
  | "requirements"
  | "tests"
  | "documents"
  | "diagrams"
  | "activity"
  | "access";
export type DownloadUrl = (path?: string, version?: number) => string;
