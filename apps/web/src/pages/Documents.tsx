import React, { useEffect, useState } from "react";
import { api, AskResp, DocEntry } from "../api";
import { Markdown } from "../markdown";

export default function DocsPage() {
  const [docs, setDocs] = useState<DocEntry[]>([]);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<AskResp | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [showCite, setShowCite] = useState<number | null>(null);

  const refresh = () => api.documents().then((r) => setDocs(r.documents)).catch(() => {});
  useEffect(() => { refresh(); }, []);

  const addFile = async (f: File) => {
    setErr("");
    if (!/\.(txt|md|markdown)$/i.test(f.name)) {
      setErr(`Chỉ hỗ trợ .txt/.md — "${f.name}" không hợp lệ.`);
      return;
    }
    if (f.size > 2 * 1024 * 1024) {
      setErr(`"${f.name}" quá lớn (giới hạn 2 MiB).`);
      return;
    }
    const text = await f.text();
    try {
      await api.addDocument(f.name, text);
      refresh();
    } catch (e) { setErr(String(e)); }
  };

  const ask = async () => {
    if (!q.trim() || busy) return;
    setBusy(true); setErr(""); setAnswer(null);
    try {
      setAnswer(await api.ask(q.trim()));
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const remove = async (id: string, name: string) => {
    if (!window.confirm(`Xoá "${name}" và toàn bộ trích dẫn của nó?`)) return;
    await api.deleteDocument(id).catch(() => {});
    refresh();
  };

  return (
    <div>
      <h1>Tài liệu</h1>
      <p className="sub">
        Chỉ file bạn chọn được index — không quét thư mục ngầm. Hỗ trợ .txt/.md UTF-8,
        tìm kiếm không cần dấu, trả lời kèm trích dẫn.
      </p>

      <div
        className="card"
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault(); setDragOver(false);
          Array.from(e.dataTransfer.files).forEach((f) => void addFile(f));
        }}
        style={dragOver ? { borderColor: "var(--accent)", borderStyle: "dashed" } : {}}
      >
        <div className="row">
          <label className="primary" style={{ padding: "7px 14px", borderRadius: 8, background: "var(--accent)", color: "#fff", cursor: "pointer", fontWeight: 500 }}>
            Chọn file .txt/.md
            <input
              type="file" multiple accept=".txt,.md,.markdown" style={{ display: "none" }}
              onChange={(e) => Array.from(e.target.files ?? []).forEach((f) => void addFile(f))}
            />
          </label>
          <span className="muted">hoặc kéo thả vào đây</span>
        </div>
        {docs.length > 0 && (
          <table className="t" style={{ marginTop: 14 }}>
            <thead><tr><th>Tài liệu</th><th>Chunks</th><th>Kích thước</th><th></th></tr></thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>{d.name}</td>
                  <td>{d.chunk_count}</td>
                  <td className="mono">{(d.size_bytes / 1024).toFixed(1)} KiB</td>
                  <td><button className="ghost" onClick={() => void remove(d.id, d.name)}>Xoá</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {err && <div className="banner err">{err}</div>}

      <div className="card">
        <div className="composer" style={{ marginTop: 0 }}>
          <textarea
            value={q}
            placeholder={docs.length ? "Hỏi về nội dung tài liệu… (không dấu cũng được)" : "Thêm tài liệu trước khi hỏi"}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !(e.nativeEvent as any).isComposing) { e.preventDefault(); void ask(); } }}
            disabled={docs.length === 0}
            aria-label="Câu hỏi về tài liệu"
          />
          <button className="primary" onClick={() => void ask()} disabled={busy || !q.trim() || docs.length === 0}>
            {busy ? "Đang hỏi…" : "Hỏi"}
          </button>
        </div>

        {answer && (
          <div style={{ marginTop: 16 }}>
            {!answer.grounded && (
              <div className="banner warn">
                Không tìm thấy nội dung liên quan trong tài liệu — câu trả lời dưới đây là
                tri thức chung của model, <strong>không phải</strong> từ tài liệu của bạn.
              </div>
            )}
            <Markdown text={answer.answer} />
            {answer.citations.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <strong>Nguồn trích dẫn:</strong>
                {answer.citations.map((c) => (
                  <div key={c.n}>
                    <button className="ghost cite" onClick={() => setShowCite(showCite === c.n ? null : c.n)}>
                      [{c.n}] {c.document}
                    </button>
                    {showCite === c.n && <div className="excerpt">{c.excerpt}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
