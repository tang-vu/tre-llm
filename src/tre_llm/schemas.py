"""Versioned shared schemas for TreLLM.

These contracts are consumed by the CLI, the FastAPI server, the web UI, and
the evaluation/training tooling. Field names are stable; human-facing strings
may be localized at render time only.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


class Evidence(StrEnum):
    """How a value was established — never mix measured and estimated numbers."""

    MEASURED = "measured"
    ESTIMATED = "estimated"
    DOCUMENTED = "documented"  # claimed by upstream docs, not tested here
    UNKNOWN = "unknown"


class Value(BaseModel):
    """A number plus its evidence label and unit."""

    value: float | None = None
    unit: str = ""
    evidence: Evidence = Evidence.UNKNOWN
    note: str = ""


# ---------------------------------------------------------------- hardware


class CpuInfo(BaseModel):
    model: str = ""
    arch: str = ""
    physical_cores: int | None = None
    logical_cores: int | None = None
    instruction_sets: list[str] = Field(default_factory=list)


class GpuInfo(BaseModel):
    vendor: str = ""
    model: str = ""
    vram_total_mb: int | None = None
    vram_free_mb: int | None = None
    driver: str = ""
    runtime_available: bool = False
    unified_memory: bool = False
    probe_status: str = "ok"  # ok | missing_tool | error


class DiskInfo(BaseModel):
    path: str
    free_bytes: int
    total_bytes: int


class HardwareSnapshot(BaseModel):
    schema_version: int = SCHEMA_VERSION
    collected_at: str
    os: str = ""
    os_version: str = ""
    machine: str = ""
    is_wsl: bool = False
    in_container: bool = False
    cpu: CpuInfo = Field(default_factory=CpuInfo)
    ram_total_mb: int | None = None
    ram_available_mb: int | None = None
    gpus: list[GpuInfo] = Field(default_factory=list)
    disks: list[DiskInfo] = Field(default_factory=list)
    python_version: str = ""
    probe_errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- registry


class ArtifactFile(BaseModel):
    path: str  # relative path inside the artifact dir
    size_bytes: int
    sha256: str | None = None  # None allowed only for non-integrity aux files


class RuntimeRequirement(BaseModel):
    runtime: str = "llama.cpp"
    min_version: str = ""  # e.g. "b11022" or semver
    backends: list[str] = Field(default_factory=lambda: ["cpu"])


class ModelArtifact(BaseModel):
    """A curated registry entry. `id` is the Tre registry id, NOT a claim of
    original authorship — upstream fields keep the real model identity."""

    schema_version: int = SCHEMA_VERSION
    id: str
    display_name: str
    upstream_repo: str  # e.g. "unsloth/Qwen3.5-0.8B-GGUF"
    upstream_model: str  # e.g. "Qwen/Qwen3.5-0.8B" base/instruct model
    publisher: str
    revision: str = "main"
    files: list[ArtifactFile]
    format: str = "gguf"
    quantization: str = ""
    architecture: str = ""  # e.g. qwen3, qwen3.5, llama
    params_billion: float = 0.0
    context_length: int | None = None
    license: str = ""
    license_url: str = ""
    source_url: str = ""
    profile: str = ""  # tiny | lite | core | pro
    tuned: str = "instruct"  # base | instruct | adaptation
    runtime: RuntimeRequirement = Field(default_factory=RuntimeRequirement)
    evidence: Evidence = Evidence.DOCUMENTED
    vietnamese_notes: str = ""
    min_ram_mb: int | None = None  # conservative floor for planning
    thinking_capable: bool = False
    # Architecture hints for memory planning (from upstream config.json).
    # hybrid models: n_layers counts all layers; full_attn_interval gives the
    # share of full-attention layers; linear_* describe the recurrent state.
    arch_meta: dict[str, Any] = Field(default_factory=dict)


class InstalledModel(BaseModel):
    """A model present on this machine (downloaded or imported)."""

    registry_id: str
    artifact: ModelArtifact | None = None  # None for imported non-registry files
    local_path: str
    sha256_actual: str = ""
    installed_at: str
    source: Literal["downloaded", "imported"] = "downloaded"
    verified: bool = True
    # Free-form provenance for imported artifacts (e.g. base_model, adapter,
    # license). Empty for registry downloads — their provenance is `artifact`.
    provenance: dict[str, str] = {}


# ---------------------------------------------------------------- runtime


class RuntimeCapabilities(BaseModel):
    schema_version: int = SCHEMA_VERSION
    runtime: str = "llama.cpp"
    build: str = ""  # e.g. "b11022" or version string
    commit: str = ""
    streaming: bool = True
    cancellation: bool = True
    token_counting: bool = True
    json_schema_output: bool = False
    tool_calling: bool = False
    thinking_control: bool = False
    embeddings: bool = False
    max_context: int | None = None
    gpu_offload: bool = False
    notes: list[str] = Field(default_factory=list)


class GenerationRequest(BaseModel):
    schema_version: int = SCHEMA_VERSION
    model: str = ""
    messages: list[dict[str, str]]
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.8
    top_k: int = 20
    presence_penalty: float = 1.5
    stream: bool = True
    enable_thinking: bool | None = None
    stop: list[str] | None = None


class GenerationEvent(BaseModel):
    """One item on the generation stream."""

    type: Literal["token", "reasoning", "done", "error", "metrics"]
    text: str = ""
    finish_reason: str = ""
    usage: dict[str, Any] | None = None
    timings: dict[str, Any] | None = None
    error: str = ""


# ---------------------------------------------------------------- planning


class Goal(StrEnum):
    LIGHT = "light"  # Nhẹ máy
    BALANCED = "balanced"  # Cân bằng
    QUALITY = "quality"  # Ưu tiên chất lượng


class MemoryEstimate(BaseModel):
    """Conservative peak-memory estimate with explicit assumptions."""

    total_mb: int | None
    evidence: Evidence = Evidence.ESTIMATED
    components: dict[str, float] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class PlanChoice(BaseModel):
    artifact_id: str
    runtime: str = "llama.cpp"
    ctx_size: int = 4096
    max_output: int = 1024
    threads: int = 0  # 0 = auto
    batch_size: int = 512
    ubatch_size: int = 512
    parallel: int = 1
    gpu_layers: int = 0
    memory: MemoryEstimate = Field(default_factory=lambda: MemoryEstimate(total_mb=None))
    feasible: bool = True
    rejection: str = ""


class DeploymentPlan(BaseModel):
    schema_version: int = SCHEMA_VERSION
    goal: Goal = Goal.BALANCED
    chosen: PlanChoice | None = None
    rejected: list[PlanChoice] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)  # Vietnamese human text
    hardware_fingerprint: str = ""
    created_at: str = ""
    supported: bool = True
    unsupported_reason: str = ""


class CalibrationResult(BaseModel):
    schema_version: int = SCHEMA_VERSION
    artifact_id: str
    status: Literal["ok", "timeout", "oom", "load_failed", "error"] = "ok"
    ttft_ms: Value = Field(default_factory=Value)
    decode_tps: Value = Field(default_factory=Value)
    prompt_tps: Value = Field(default_factory=Value)
    peak_rss_mb: Value = Field(default_factory=Value)
    load_ms: Value = Field(default_factory=Value)
    settings: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    measured_at: str = ""
    fingerprint: str = ""


# ---------------------------------------------------------------- evaluation


class EvalItem(BaseModel):
    id: str
    category: str
    split: Literal["dev", "test"] = "test"
    language_notes: str = ""
    provenance: str = "synthetic"  # synthetic | curated | external:<src>
    license: str = "CC-BY-4.0"
    prompt: str
    system: str = ""
    expected: Any = None
    grading: dict[str, Any] = Field(default_factory=dict)
    max_tokens: int = 512


class EvalResult(BaseModel):
    item_id: str
    response: str = ""
    reasoning: str = ""
    score: float | None = None  # None => ungraded (rubric item without judge)
    passed: bool | None = None
    grader: str = "deterministic"  # deterministic | rubric-ungraded | judge:<model>
    detail: str = ""
    latency_ms: float | None = None
    error: str = ""


class EvaluationReport(BaseModel):
    schema_version: int = SCHEMA_VERSION
    suite: str = "tre-viet"
    suite_version: str = ""
    split: str = "test"
    model_id: str = ""
    artifact_sha256: str = ""
    runtime_build: str = ""
    hardware_fingerprint: str = ""
    started_at: str = ""
    finished_at: str = ""
    results: list[EvalResult] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class PerformanceReport(BaseModel):
    schema_version: int = SCHEMA_VERSION
    model_id: str = ""
    artifact_sha256: str = ""
    runtime_build: str = ""
    hardware: HardwareSnapshot | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    load_ms: Value = Field(default_factory=Value)
    cold_request_ms: Value = Field(default_factory=Value)
    warm_request_ms: Value = Field(default_factory=Value)
    ttft_ms: Value = Field(default_factory=Value)
    decode_tps: Value = Field(default_factory=Value)
    chars_per_second: Value = Field(default_factory=Value)
    prompt_tps: Value = Field(default_factory=Value)
    peak_rss_mb: Value = Field(default_factory=Value)
    samples: int = 0
    failures: int = 0
    measured_at: str = ""
    notes: list[str] = Field(default_factory=list)

    def summary_vi(self) -> str:
        """Human-readable Vietnamese summary for CLI output."""
        lines = [f"Model: {self.model_id} — runtime {self.runtime_build}"]
        if self.samples == 0:
            lines.append("Không có mẫu đo thành công.")
        else:
            for label, v in (
                ("Load model", self.load_ms),
                ("TTFT", self.ttft_ms),
                ("Decode", self.decode_tps),
                ("Prompt", self.prompt_tps),
                ("RSS đỉnh", self.peak_rss_mb),
            ):
                if v.value is not None:
                    lines.append(f"  {label}: {v.value} {v.unit} [{v.evidence.value}]")
            lines.append(f"  Mẫu: {self.samples} thành công, {self.failures} lỗi")
        lines += [f"  · {n}" for n in self.notes]
        return "\n".join(lines)
