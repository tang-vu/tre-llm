// TreLLM web API client — same-origin, no CDN, no telemetry.

export interface Status {
  version: string;
  active_model: string;
  upstream_ready: boolean;
  installed: string[];
}

export interface Hardware {
  os: string; os_version: string; machine: string; is_wsl: boolean; in_container: boolean;
  cpu: { model: string; arch: string; physical_cores: number | null; logical_cores: number | null; instruction_sets: string[] };
  ram_total_mb: number | null; ram_available_mb: number | null;
  gpus: { vendor: string; model: string; vram_total_mb: number | null; vram_free_mb: number | null; driver: string; runtime_available: boolean }[];
  disks: { path: string; free_bytes: number; total_bytes: number }[];
  probe_errors: string[];
}

export interface Plan {
  supported: boolean; unsupported_reason: string; explanation: string[];
  chosen: null | {
    artifact_id: string; ctx_size: number; max_output: number; threads: number;
    memory: { total_mb: number | null; evidence: string; components: Record<string, number>; assumptions: string[] };
  };
  rejected: { artifact_id: string; feasible: boolean; rejection: string; memory: { total_mb: number | null } }[];
}

export interface ModelEntry {
  id: string; display_name: string; upstream_repo: string; quantization: string;
  params_billion: number; license: string; profile: string; evidence: string;
  vietnamese_notes: string; files: { size_bytes: number }[];
}

export interface ModelsResp {
  registry: ModelEntry[];
  installed: Record<string, { local_path: string; sha256_actual: string; source: string }>;
  active: string | null;
}

export interface DocEntry {
  id: string; name: string; size_bytes: number; status: string; chunk_count: number; created_at: string;
}

export interface Citation { n: number; chunk_id: string; document: string; excerpt: string; offset: number }
export interface AskResp { answer: string; citations: Citation[]; grounded: boolean }

export interface ConvEntry { id: string; title: string; model_id: string; created_at: string; updated_at: string }
export interface ConvMsg { seq: number; role: string; content: string; reasoning: string }

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = `${r.status}`;
    try { detail = (await r.json()).detail || detail; } catch { /* keep status */ }
    throw new Error(String(detail));
  }
  return r.json() as Promise<T>;
}

export const api = {
  status: () => fetch("/api/status").then(r => j<Status>(r)),
  hardware: () => fetch("/api/hardware").then(r => j<Hardware>(r)),
  plan: (goal = "balanced") => fetch(`/api/plan?goal=${goal}`).then(r => j<Plan>(r)),
  models: () => fetch("/api/models").then(r => j<ModelsResp>(r)),
  selectModel: (id: string) => fetch("/api/models/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model_id: id }) }).then(r => j(r)),
  deleteModel: (id: string) => fetch(`/api/models/${id}`, { method: "DELETE" }).then(r => j(r)),
  documents: () => fetch("/api/documents").then(r => j<{ documents: DocEntry[] }>(r)),
  addDocument: (name: string, content: string, contentBase64?: string) => fetch("/api/documents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(contentBase64 ? { name, content_base64: contentBase64 } : { name, content }) }).then(r => j(r)),
  deleteDocument: (id: string) => fetch(`/api/documents/${id}`, { method: "DELETE" }).then(r => j(r)),
  docChunks: (id: string) => fetch(`/api/documents/${id}`).then(r => j(r)),
  ask: (question: string, k = 4) => fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, k }) }).then(r => j<AskResp>(r)),
  conversations: () => fetch("/api/conversations").then(r => j<ConvEntry[]>(r)),
  convMessages: (id: string) => fetch(`/api/conversations/${id}/messages`).then(r => j<{ messages: ConvMsg[] }>(r)),
  newConversation: () => fetch("/api/conversations", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then(r => j<{ id: string }>(r)),
  deleteConversation: (id: string) => fetch(`/api/conversations/${id}`, { method: "DELETE" }).then(r => j(r)),
  bench: () => fetch("/api/bench", { method: "POST" }).then(r => j<{ run_id: string }>(r)),
  runStatus: (id: string) => fetch(`/api/runs/${id}`).then(r => j<{ status: string; result?: string; error?: string }>(r)),
  reports: () => fetch("/api/reports").then(r => j<{ reports: { name: string; size: number }[] }>(r)),
  cancel: () => fetch("/api/cancel", { method: "POST" }).then(r => j(r)),
};

export type ChatEvent =
  | { type: "conv"; id: string }
  | { type: "token"; text: string }
  | { type: "reasoning"; text: string }
  | { type: "done"; finish_reason: string; timings?: { predicted_per_second?: number; prompt_per_second?: number } }
  | { type: "error"; error: string };

export async function* streamChat(
  body: { conversation_id?: string; message: string; max_tokens?: number; enable_thinking?: boolean },
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder("utf-8");
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, i);
      buf = buf.slice(i + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (data === "[DONE]") return;
        try { yield JSON.parse(data) as ChatEvent; } catch { /* skip */ }
      }
    }
  }
}
