import React from "react";
import { ImportEntry, ImportQueue } from "./importQueue";

const LABELS = { pending: "Đang chờ", uploading: "Đang đọc và nhập…", success: "Đã nhập", failure: "Không nhập được" };

export function ImportList({ entries, queue, onRetry }: { entries: ImportEntry[]; queue: ImportQueue; onRetry: (id: number) => void }) {
  if (!entries.length) return null;
  const done = entries.filter(entry => entry.status === "success").length;
  const failed = entries.filter(entry => entry.status === "failure").length;
  const active = entries.length - done - failed;
  return <section className="import-queue" aria-label="Hàng đợi nhập tài liệu">
    <div className="row">
      <strong role="status">{done} đã nhập · {failed} lỗi/chưa rõ · {active} đang chờ/xử lý</strong>
      <button className="ghost" disabled={!done && !failed} onClick={() => queue.clearFinished()}>Dọn kết quả</button>
    </div>
    <ul className="import-list">
      {entries.map(entry => <li key={entry.id}>
        <div className="import-detail">
          <strong className="file-name">{entry.name}</strong>
          <span className="muted">{(entry.size / 1024).toFixed(1)} KiB</span>
          <span className={`chip ${entry.status === "success" ? "ok" : entry.status === "failure" ? "err" : ""}`}>{entry.uncertain ? "Chưa rõ kết quả" : LABELS[entry.status]}</span>
          {entry.error && <div className="import-error">{entry.error}</div>}
          {entry.uncertain && <div className="muted">Chưa xác nhận được kết quả. File có thể đã được thêm; kiểm tra danh sách trước khi thử lại để tránh bản trùng.</div>}
        </div>
        <div className="row">
          {entry.status === "failure" && entry.retryable && <button onClick={() => onRetry(entry.id)} aria-label={`Thử lại ${entry.name}`}>Thử lại</button>}
          {entry.status !== "uploading" && <button className="ghost" onClick={() => queue.dismiss(entry.id)} aria-label={`${entry.status === "pending" ? "Bỏ qua" : "Ẩn kết quả"} ${entry.name}`}>{entry.status === "pending" ? "Bỏ qua" : "Ẩn"}</button>}
        </div>
      </li>)}
    </ul>
    <p className="muted">Dọn hoặc ẩn kết quả không xoá tài liệu đã nhập.</p>
  </section>;
}
