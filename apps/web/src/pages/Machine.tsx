import React, { useEffect, useState } from "react";
import { api, Hardware, Plan } from "../api";

function gib(b: number | null | undefined) {
  return b == null ? "—" : `${(b / 2 ** 30).toFixed(1)} GiB`;
}
function mib(b: number | null | undefined) {
  return b == null ? "—" : `${b} MiB`;
}

export default function MachinePage() {
  const [hw, setHw] = useState<Hardware | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [goal, setGoal] = useState("balanced");
  const [err, setErr] = useState("");

  useEffect(() => {
    api.hardware().then(setHw).catch((e) => setErr(String(e)));
  }, []);
  useEffect(() => {
    api.plan(goal).then(setPlan).catch(() => setPlan(null));
  }, [goal]);

  return (
    <div>
      <h1>Máy của bạn</h1>
      <p className="sub">Phần cứng phát hiện thật và kế hoạch triển khai được giải thích.</p>
      {err && <div className="banner err">Không đọc được phần cứng: {err}</div>}
      {hw && (
        <div className="card">
          <dl className="kv">
            <dt>Hệ điều hành</dt>
            <dd>
              {hw.os} {hw.is_wsl ? "(WSL2)" : ""} {hw.in_container ? "— container" : ""}
            </dd>
            <dt>CPU</dt>
            <dd>
              {hw.cpu.model} — {hw.cpu.physical_cores ?? "?"}C/{hw.cpu.logical_cores ?? "?"}T
            </dd>
            <dt>RAM</dt>
            <dd>{mib(hw.ram_total_mb)} tổng · {mib(hw.ram_available_mb)} khả dụng</dd>
            <dt>GPU</dt>
            <dd>
              {hw.gpus.length === 0 && "Không phát hiện — chế độ CPU"}
              {hw.gpus.map((g, i) => (
                <div key={i}>
                  {g.vendor} {g.model} — VRAM trống {mib(g.vram_free_mb)}/{mib(g.vram_total_mb)}
                  {!g.runtime_available && <span className="chip warn">driver chưa sẵn sàng</span>}
                </div>
              ))}
            </dd>
            <dt>Disk trống</dt>
            <dd>{hw.disks.map((d, i) => <div key={i} className="mono">{d.path}: {gib(d.free_bytes)}</div>)}</dd>
            {hw.probe_errors.length > 0 && (
              <>
                <dt>Probe lỗi</dt>
                <dd className="muted">{hw.probe_errors.join("; ")}</dd>
              </>
            )}
          </dl>
        </div>
      )}

      <div className="card">
        <div className="toolbar">
          <strong>Kế hoạch đề xuất</strong>
          <div className="row" role="group" aria-label="Mục tiêu">
            {([["light", "Nhẹ máy"], ["balanced", "Cân bằng"], ["quality", "Ưu tiên chất lượng"]] as const).map(
              ([g, label]) => (
                <button
                  key={g}
                  className={goal === g ? "primary" : ""}
                  onClick={() => setGoal(g)}
                >
                  {label}
                </button>
              ),
            )}
          </div>
        </div>
        {plan?.supported && plan.chosen ? (
          <>
            <ul>
              {plan.explanation.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
            <details className="exp">
              <summary>Chi tiết kỹ thuật &amp; phương án bị loại</summary>
              <table className="t">
                <thead>
                  <tr><th>Model</th><th>RAM ước lượng</th><th>Trạng thái</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>{plan.chosen.artifact_id}</strong> (chọn)</td>
                    <td>{mib(plan.chosen.memory.total_mb)} <span className="chip">{plan.chosen.memory.evidence}</span></td>
                    <td><span className="chip ok">khả thi</span></td>
                  </tr>
                  {plan.rejected.map((r) => (
                    <tr key={r.artifact_id}>
                      <td>{r.artifact_id}</td>
                      <td>{mib(r.memory.total_mb)}</td>
                      <td>{r.feasible ? "khả thi — không được chọn theo mục tiêu" : <span className="chip err">{r.rejection}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </>
        ) : (
          <div className="banner warn">{plan?.unsupported_reason || "Đang phân tích…"}</div>
        )}
      </div>
    </div>
  );
}
