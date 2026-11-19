import type { ReactNode } from "react";
import type { DocKind } from "../types";
import {
  CheckCheck,
  Code2,
  FileText,
  Layers3,
  Network,
  ShieldCheck,
} from "lucide-react";

export const DOCS: {
  id: DocKind;
  title: string;
  description: string;
  icon: typeof FileText;
}[] = [
  {
    id: "srs",
    title: "Requirements specification",
    description: "As-is functionality and business rules",
    icon: FileText,
  },
  {
    id: "requirements_signoff",
    title: "Requirements sign-off",
    description: "Baseline review and human approval",
    icon: CheckCheck,
  },
  {
    id: "test_cases",
    title: "Test cases & UAT report",
    description: "Scenarios and requirements traceability",
    icon: ShieldCheck,
  },
  {
    id: "uat_signoff",
    title: "Application acceptance",
    description: "UAT outcomes and stakeholder decisions",
    icon: CheckCheck,
  },
  {
    id: "architecture",
    title: "System architecture",
    description: "Components and their relationships",
    icon: Layers3,
  },
  {
    id: "data_flow",
    title: "Data flow diagrams",
    description: "Context, processes and handler detail",
    icon: Network,
  },
  {
    id: "technology",
    title: "Technology stack",
    description: "Languages, frameworks and dependencies",
    icon: Code2,
  },
];
export const providerNames = {
  openai: "OpenAI",
  anthropic: "Anthropic Claude",
  gemini: "Google Gemini",
};
export const time = (value: string) =>
  new Date(value.endsWith("Z") ? value : value + "Z").toLocaleString();
export const human = (value: string) => value.replaceAll("_", " ");
export const Badge = ({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) => <span className={`badge ${tone}`}>{children}</span>;
