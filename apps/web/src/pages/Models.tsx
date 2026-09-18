import React, { useEffect, useState } from "react";
import { api, ModelsResp } from "../api";

function mb(bytes: number) { return (bytes / 2 ** 20).toFixed(0) + " MiB"; }

export default function ModelsPage() {
  const [data, setData] = useState<ModelsResp | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const refresh = () => api.models().then(setData).catch((e) => setErr(String(e)));
  useEffect(() => { refresh(); }, []);

  const select = async (id: string) => {
    setErr(""); setMsg("");
    try {
      const r = (await api.selectModel(id)) as {
        applied?: boolean; note?: string; adjustments?: string[];
      };
      const adj = r.adjustments?.length ? ` Phục hồi: ${r.adjustments.join("; ")}` : "";
      setMsg(
        r.applied === false
          ? `Đã lưu ${id}. ${r.note ?? ""}`
          : `Đang chạy ${id} (đổi nóng, không cần restart).${adj}${r.note ? " " + r.note : ""}`,
      );
      refresh();
    }
    catch (e) { setErr(String(e)); }
  };

  const remove = async (id: string) => {
    if (!window.confirm(`Xoá "${id}" khỏi máy? Registry vẫn giữ metadata.`)) return;
    await api.deleteModel(id).catch((e) => setErr(String(e)));
    refresh();
  };

  return (
    <div>
      <h1>Mô hình &amp; cài đặt</h1>
      <p className="sub">
        Danh tính upstream thật — TreLLM không tự huấn luyện các model này.
      </p>
      {err && <div className="banner err">{err}</div>}
      {msg && <div className="banner info">{msg}</div>}

      <div className="card">
        <table className="t">
          <thead>
            <tr><th>Profile</th><th>Upstream</th><th>Quant</th><th>Kích thước</th><th>Evidence</th><th></th></tr>
          </thead>
          <tbody>
            {data?.registry.map((m) => {
              const inst = data.installed[m.id];
              const active = data.active === m.id;
              return (
                <tr key={m.id}>
                  <td>
                    <span className="chip">{m.profile}</span>
                    <div style={{ marginTop: 4, fontWeight: 600 }}>{m.display_name}</div>
                    <div className="muted" style={{ fontSize: 12 }}>{m.params_billion}B · {m.license}</div>
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>{m.upstream_repo}</td>
                  <td>{m.quantization}</td>
                  <td className="mono">{mb(m.files.reduce((a, f) => a + f.size_bytes, 0))}</td>
                  <td><span className={`chip ${m.evidence === "verified" ? "ok" : "warn"}`}>{m.evidence}</span></td>
                  <td>
                    {active ? <span className="chip ok">đang chạy</span> : (
                      <button className="ghost" onClick={() => void select(m.id)} disabled={!inst}>
                        {inst ? "Kích hoạt" : "chưa cài"}
                      </button>
                    )}
                    {inst && !active && <button className="ghost" onClick={() => void remove(m.id)}>Xoá file</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {data?.registry.some((m) => m.vietnamese_notes) && (
          <div style={{ marginTop: 12 }} className="muted">
            <strong>Lưu ý tiếng Việt:</strong>
            <ul>
              {data.registry.filter((m) => m.vietnamese_notes).map((m) => (
                <li key={m.id}><em>{m.display_name}:</em> {m.vietnamese_notes}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="card">
        <strong>Quyền riêng tư &amp; lưu trữ</strong>
        <ul className="muted" style={{ marginBottom: 0 }}>
          <li>Mọi suy luận chạy trên máy này qua llama.cpp — không gọi API bên ngoài lúc chat.</li>
          <li>Hội thoại và tài liệu lưu trong SQLite tại thư mục dữ liệu cục bộ.</li>
          <li>Mạng chỉ dùng khi tải model từ Hugging Face lần đầu — bạn có thể kiểm chứng bằng cách tắt mạng sau khi setup.</li>
          <li>Không tài khoản, không email, không telemetry.</li>
        </ul>
      </div>
    </div>
  );
}
