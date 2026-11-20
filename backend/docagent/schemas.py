from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Confidence(StrEnum):
    verified = "verified"
    inferred = "inferred"
    missing = "missing"


class Evidence(StrictModel):
    id: str
    path: str
    start_line: int
    end_line: int
    symbol: str = ""
    snippet: str = ""
    commit: str = ""


class Finding(StrictModel):
    id: str
    kind: str
    title: str
    detail: str
    confidence: Confidence = Confidence.verified
    evidence_ids: list[str]
    metadata: dict = Field(default_factory=dict)


class Requirement(StrictModel):
    id: str
    title: str
    statement: str
    confidence: Confidence
    evidence_ids: list[str]
    module: str
    source: Literal["static", "llm", "reviewer"] = "static"


class TestCase(StrictModel):
    id: str
    requirement_id: str
    title: str
    category: str
    preconditions: list[str]
    steps: list[str]
    expected: str
    status: Literal["unexecuted"] = "unexecuted"
    source: Literal["static", "llm"] = "static"


class ProviderSelection(StrictModel):
    provider: Literal["openai", "anthropic", "gemini"]
    model: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9._:/-]+$")


DOCUMENTS = [
    "srs",
    "requirements_signoff",
    "test_cases",
    "uat_signoff",
    "data_flow",
    "architecture",
    "technology",
]


class AnalysisConfig(StrictModel):
    repository: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}$", max_length=140)
    ref: str = Field(default="", max_length=250)
    depth: Literal["basic", "standard", "comprehensive"] = "standard"
    documents: list[
        Literal[
            "srs",
            "requirements_signoff",
            "test_cases",
            "uat_signoff",
            "data_flow",
            "architecture",
            "technology",
        ]
    ] = Field(default_factory=lambda: DOCUMENTS.copy(), min_length=1)
    formats: list[Literal["md", "docx", "pdf"]] = Field(default_factory=lambda: ["md", "docx"], min_length=1)
    providers: list[ProviderSelection] = Field(default_factory=list, max_length=3)
    consent_providers: list[Literal["openai", "anthropic", "gemini"]] = Field(default_factory=list)
    execute_tests: bool = False
    test_profile: Literal["pytest", "npm"] = "pytest"

    @field_validator("repository")
    @classmethod
    def valid_repository(cls, value):
        if value.split("/")[1] in {".", ".."}:
            raise ValueError("Invalid repository name")
        return value

    @field_validator("ref")
    @classmethod
    def valid_ref(cls, value):
        if any(ord(c) < 32 for c in value) or value.startswith("-"):
            raise ValueError("Invalid Git reference")
        return value

    @model_validator(mode="after")
    def unique(self):
        self.documents = list(dict.fromkeys(self.documents))
        self.formats = list(dict.fromkeys(self.formats))
        if len({p.provider for p in self.providers}) != len(self.providers):
            raise ValueError("Select each provider only once")
        return self


class LLMScenario(StrictModel):
    title: str
    category: Literal["positive", "negative", "boundary", "authentication", "authorization", "integration"]
    preconditions: list[str]
    steps: list[str]
    expected: str


class LLMRequirement(StrictModel):
    title: str
    statement: str
    evidence_ids: list[str]
    scenarios: list[LLMScenario] = Field(default_factory=list, max_length=3)


class LLMOutput(StrictModel):
    requirements: list[LLMRequirement] = Field(max_length=6)
    gaps: list[str]


class ReviewInput(StrictModel):
    stage: Literal["requirements", "uat"]
    decision: Literal["approved", "changes_requested", "comment"]
    comment: str = Field(min_length=1, max_length=4000)
    baseline_hash: str = Field(min_length=64, max_length=64)
    acknowledged: bool = False


class ResultInput(StrictModel):
    baseline_hash: str = Field(min_length=64, max_length=64)
    test_case_id: str
    status: Literal["passed", "failed", "blocked"]
    actual: str = Field(min_length=10, max_length=5000)
    evidence_reference: str = Field(min_length=5, max_length=1000)
    source: Literal["manual_uat", "existing_report"]
    severity: Literal["none", "low", "medium", "high", "critical"] = "none"
    attested: bool


class RequirementEdit(StrictModel):
    statement: str = Field(min_length=10, max_length=4000)
    rationale: str = Field(min_length=5, max_length=2000)
    baseline_hash: str


class CollaboratorInput(StrictModel):
    login: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
    role: Literal["viewer", "reviewer"]
    acknowledged: bool
