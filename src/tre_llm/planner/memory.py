"""Conservative memory estimation for llama.cpp deployments.

Estimate = weights (file size) + context state + compute buffers + margin.

Context state is architecture-aware:
- standard transformer: KV = ctx * n_layers * kv_heads * head_dim * 2 (K+V) * dtype_bytes
- hybrid linear/full attention (e.g. Qwen3.5): KV only for the full-attention
  layers; linear layers keep a fixed recurrent state independent of ctx.
- unknown arch: conservative bound treating every layer as full attention with
  a wide head count — explicitly labelled.

Prefill peaks are tracked separately where batch/ubatch buffers dominate.
"""

from __future__ import annotations

from tre_llm.schemas import Evidence, MemoryEstimate, ModelArtifact

KV_DTYPE_BYTES = 2  # f16 KV default
COMPUTE_BUFFER_FRACTION = 0.08  # llama.cpp compute buffers ~ a few % of weights
MIN_COMPUTE_MB = 128
SAFETY_FRACTION = 0.15
SERVER_OVERHEAD_MB = 120  # server binary + runtime + misc


def _full_attn_layers(arch: dict) -> float:
    n = float(arch.get("n_layers") or 0)
    if not n:
        return 0
    if arch.get("hybrid"):
        interval = float(arch.get("full_attn_interval") or 4)
        return max(1.0, n / interval)
    return n


def kv_cache_mb(artifact: ModelArtifact, ctx_size: int) -> tuple[float, list[str]]:
    """KV+state size in MiB for one sequence of `ctx_size` tokens."""
    a = artifact.arch_meta
    notes: list[str] = []
    n_layers = a.get("n_layers")
    if not n_layers:
        # Unknown arch — conservative bound: assume dense transformer,
        # hidden 2048, 32 layers, kv_heads=8, head_dim=128.
        bound = ctx_size * 32 * 8 * 128 * 2 * KV_DTYPE_BYTES / 2**20
        notes.append("Kiến trúc chưa rõ → chặn trên transformer tiêu chuẩn (32 lớp, GQA 8×128).")  # noqa: RUF001
        return bound, notes

    full_layers = _full_attn_layers(a)
    kv_heads = float(a.get("kv_heads") or 8)
    head_dim = float(a.get("head_dim") or 128)
    kv = ctx_size * full_layers * kv_heads * head_dim * 2 * KV_DTYPE_BYTES / 2**20

    state = 0.0
    if a.get("hybrid"):
        # Recurrent state per linear layer: key_heads * key_dim * val_dim * 4B
        # plus a small conv state. Independent of ctx.
        lin_layers = n_layers - full_layers
        k = float(a.get("linear_kv_heads") or 16)
        kd = float(a.get("linear_key_dim") or 128)
        vd = float(a.get("linear_val_dim") or 128)
        state = lin_layers * (k * kd * vd * 4 + k * kd * 4 * 4) / 2**20
        notes.append(
            f"Kiến trúc hybrid: chỉ {int(full_layers)}/{int(n_layers)} lớp full-attention "
            f"dùng KV; {int(lin_layers)} lớp tuyến tính giữ state cố định ~{state:.0f} MiB."
        )
    return kv + state, notes


def estimate(
    artifact: ModelArtifact,
    ctx_size: int,
    parallel: int = 1,
    batch_size: int = 512,
) -> MemoryEstimate:
    """Peak host-memory estimate (MiB) for one server process."""
    weights_mb = sum(f.size_bytes for f in artifact.files) / 2**20
    kv_mb, notes = kv_cache_mb(artifact, ctx_size)
    kv_total = kv_mb * max(1, parallel)

    compute = max(MIN_COMPUTE_MB, weights_mb * COMPUTE_BUFFER_FRACTION)
    # Prefill chunk buffer scales with ubatch tokens, not full ctx.
    prefill_tokens = min(batch_size, ctx_size)
    prefill_extra = prefill_tokens * artifact.params_billion * 0.02  # rough activation bound
    notes.append("Prefill activation buffer ước lượng thô (~2% params × batch tokens).")  # noqa: RUF001

    subtotal = weights_mb + kv_total + compute + prefill_extra + SERVER_OVERHEAD_MB
    total = subtotal * (1 + SAFETY_FRACTION)
    return MemoryEstimate(
        total_mb=round(total),
        evidence=Evidence.ESTIMATED,
        components={
            "weights_mb": round(weights_mb),
            "kv_state_mb": round(kv_total),
            "compute_buffer_mb": round(compute),
            "prefill_buffer_mb": round(prefill_extra),
            "server_overhead_mb": SERVER_OVERHEAD_MB,
            "safety_margin_mb": round(subtotal * SAFETY_FRACTION),
        },
        assumptions=[
            f"KV dtype f16 ({KV_DTYPE_BYTES}B/phần tử), {parallel} luồng song song.",
            f"Weights mmap từ file {weights_mb:.0f} MiB.",
            "Chặn an toàn +15% cho fragment/buffers phụ.",
            *notes,
        ],
    )
