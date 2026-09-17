import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";

export default function LabPage() {
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState("");
  const [status, setStatus] = useState("");
  const [result, setResult] = useState("");
  const [err, setErr] = useState("");
  const [reports, setReports] = useState<{ name: string; size: number }[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshReports = () => api.reports().then((r) => setReports(r.reports)).catch(() => {});
  useEffect(() => { refreshReports(); return () => { if (pollRef.current) clearInterval(pollRef.current); }; }, []);

  const runBench = async () => {
    setBusy(true); setErr(""); setResult(""); setStatus("queued");
    try {
      const r = await api.bench();
      setRunId(r.run_id);
      pollRef.current = setInterval(async () => {
        try {
          const s = await api.runStatus(r.run_id);
          setStatus(s.status);
          if (s.status === "done" || s.status === "error") {
            if (pollRef.current) clearInterval(pollRef.current);
            setBusy(false);
            if (s.status === "done" && s.result) {
              setResult(s.result); // summary_vi() — preformatted Vietnamese text
              refreshReports();
            } else if (s.error) setErr(s.error);
          }
        } catch { /* keep polling */ }
      }, 1500);
    } catch (e) { setErr(String(e)); setBusy(false); }
  };

  return (
    <div>
      <h1>Phòng thử</h1>
      <p className="sub">
        Đo hiệu năng thật trên máy này — không số liệu mẫu, không benchmark bịa.
      </p>

      <div className="card">
        <div className="row">
          <button className="primary" onClick={() => void runBench()} disabled={busy}>
            {busy ? `Đang đo… (${status})` : "Chạy đo hiệu năng"}
          </button>
          <span className="muted">Prompt cố định tiếng Việt, số mẫu giới hạn, kết quả lưu vào evidence/.</span>
        </div>
        {result && <pre className="code" style={{ marginTop: 12, whiteSpace: "pre-wrap" }}>{result}</pre>}
        {err && <div className="banner err" style={{ marginTop: 12 }}>{err}</div>}
      </div>

      <div className="card">
        <strong>Báo cáo đã lưu</strong>
        {reports.length === 0 ? (
          <p className="muted">Chưa có báo cáo nào.</p>
        ) : (
          <table className="t" style={{ marginTop: 10 }}>
            <thead><tr><th>File</th><th>Kích thước</th></tr></thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.name}>
                  <td className="mono">{r.name}</td>
                  <td className="mono">{(r.size / 1024).toFixed(1)} KiB</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
