import React, { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api, AskResp, DocEntry } from "../api";
import { Markdown } from "../markdown";
import { ImportQueue } from "../documents/importQueue";
import { ImportList } from "../documents/ImportList";

export default function DocsPage() {
  const [docs, setDocs] = useState<DocEntry[]>([]);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<AskResp | null>(null);
  const [busy, setBusy] = useState(false);
  const [askError, setAskError] = useState("");
  const [listError, setListError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [queue] = useState(() => new ImportQueue());
  const imports = useSyncExternalStore(queue.subscribe, queue.getSnapshot);
  const importing = imports.entries.some(entry => entry.status === "pending" || entry.status === "uploading");
  const fileInput = useRef<HTMLInputElement>(null);
  const mounted = useRef(false);
  const refreshId = useRef(0);
  const askId = useRef(0);
  const asking = useRef(false);
  const deletingId = useRef<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [showCite, setShowCite] = useState<number | null>(null);

  const clearAnswer = useCallback(() => {
    askId.current++;
    asking.current = false;
    setBusy(false);
    setAnswer(null);
    setShowCite(null);
    setAskError("");
  }, []);

  const refresh = useCallback(async () => {
    const id = ++refreshId.current;
    setLoading(true);
    setListError("");
    try {
      const response = await api.documents();
      if (!mounted.current || id !== refreshId.current) return;
      setDocs(response.documents);
      clearAnswer();
    } catch (error) {
      if (mounted.current && id === refreshId.current) setListError(`Không tải được danh sách tài liệu: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      if (mounted.current && id === refreshId.current) setLoading(false);
    }
  }, [clearAnswer]);

  useEffect(() => {
    mounted.current = true;
    queue.start();
    return () => {
      mounted.current = false;
      refreshId.current++;
      askId.current++;
      queue.stop();
    };
  }, [queue]);
  useEffect(() => { void refresh(); }, [refresh, imports.settled]);
  useEffect(() => {
    if (!importing) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [importing]);

  const addFiles = (files: File[]) => {
    if (!files.length) return;
    clearAnswer();
    queue.enqueue(files);
  };
  const retry = (id: number) => { clearAnswer(); queue.retry(id); };

  const ask = async () => {
    if (!q.trim() || asking.current || importing || deletingId.current || !docs.length || loading) return;
    clearAnswer();
    const id = ++askId.current;
    asking.current = true;
    setBusy(true);
    try {
      const response = await api.ask(q.trim());
      if (mounted.current && id === askId.current) setAnswer(response);
    } catch (error) {
      if (mounted.current && id === askId.current) setAskError(error instanceof Error ? error.message : String(error));
    } finally {
      if (mounted.current && id === askId.current) { asking.current = false; setBusy(false); }
    }
  };

  const remove = async (id: string, name: string) => {
    if (deletingId.current || !window.confirm(`Xoá "${name}" và toàn bộ trích dẫn của nó?`)) return;
    deletingId.current = id;
    setDeleting(id);
    setDeleteError("");
    clearAnswer();
    try {
      await api.deleteDocument(id);
      if (!mounted.current) return;
      setDocs(current => current.filter(doc => doc.id !== id));
      clearAnswer();
      void refresh();
    } catch (error) {
      if (mounted.current) setDeleteError(`Không xoá được "${name}": ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      deletingId.current = null;
      if (mounted.current) setDeleting(null);
    }
  };

  return (
    <div>
      <h1>Tài liệu</h1>
      <p className="sub">
        Chỉ file bạn chọn được index — không quét thư mục ngầm. Hỗ trợ .txt/.md UTF-8
        và .pdf có text layer (PDF scan cần OCR — chưa hỗ trợ). Tìm kiếm không cần dấu,
        trả lời kèm trích dẫn.
      </p>

      <div
        className="card"
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault(); setDragOver(false);
          addFiles(Array.from(e.dataTransfer.files));
        }}
        style={dragOver ? { borderColor: "var(--accent)", borderStyle: "dashed" } : {}}
      >
        <div className="row">
          <button className="primary" onClick={() => fileInput.current?.click()}>Chọn file .txt/.md/.pdf</button>
          <input
            ref={fileInput} type="file" multiple accept=".txt,.md,.markdown,.pdf" hidden
            aria-label="Chọn file tài liệu"
            onChange={(event) => {
              const files = Array.from(event.currentTarget.files ?? []);
              event.currentTarget.value = "";
              addFiles(files);
            }}
          />
          <span className="muted">hoặc kéo thả vào đây</span>
        </div>
        <p className="muted import-help">Tối đa 20 file trong hàng đợi, 4 MiB/file; nhập lần lượt trên máy này. Rời trang sẽ bỏ các file đang chờ; file đang xử lý có thể vẫn được thêm.</p>
        {imports.notice && <div className="banner info" role="status">{imports.notice}</div>}
        <ImportList entries={imports.entries} queue={queue} onRetry={retry} />
        <div className="row">
          <strong>Tài liệu đã nhập ({docs.length})</strong>
          <button className="ghost" onClick={() => void refresh()} disabled={loading}>Tải lại danh sách</button>
        </div>
        {loading && <p role="status" className="muted">Đang tải danh sách…</p>}
        {listError && <div className="banner err" role="alert">{listError} Tài liệu đã nhập vẫn được giữ lại. Hãy tải lại danh sách.</div>}
        {deleteError && <div className="banner err" role="alert">{deleteError}</div>}
        {!loading && !listError && !docs.length && <p className="muted">Chưa có tài liệu. Chọn hoặc kéo thả file để bắt đầu.</p>}
        {docs.length > 0 && (
          <table className="t" style={{ marginTop: 14 }}>
            <thead><tr><th>Tài liệu</th><th>Chunks</th><th>Kích thước</th><th><span className="sr-only">Thao tác</span></th></tr></thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td className="file-name">{d.name}</td>
                  <td>{d.chunk_count}</td>
                  <td className="mono">{(d.size_bytes / 1024).toFixed(1)} KiB</td>
                  <td><button className="ghost" disabled={deleting !== null} onClick={() => void remove(d.id, d.name)} aria-label={`Xoá ${d.name}`}>{deleting === d.id ? "Đang xoá…" : "Xoá"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {askError && <div className="banner err" role="alert">{askError}</div>}

      <div className="card">
        {importing && <p className="muted" role="status">Chờ nhập xong để hỏi trên danh sách tài liệu mới nhất.</p>}
        <div className="composer" style={{ marginTop: 0 }}>
          <textarea
            value={q}
            placeholder={docs.length ? "Hỏi về nội dung tài liệu… (không dấu cũng được)" : "Thêm tài liệu trước khi hỏi"}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !(e.nativeEvent as any).isComposing) { e.preventDefault(); void ask(); } }}
            disabled={docs.length === 0}
            aria-label="Câu hỏi về tài liệu"
          />
          <button className="primary" onClick={() => void ask()} disabled={busy || importing || deleting !== null || loading || !q.trim() || docs.length === 0}>
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
