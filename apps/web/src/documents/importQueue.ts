import { api, ApiError } from "../api";

export const MAX_IMPORTS = 20;
export const MAX_FILE_BYTES = 4 * 1024 * 1024;
export type ImportStatus = "pending" | "uploading" | "success" | "failure";
export interface ImportEntry {
  id: number;
  name: string;
  size: number;
  status: ImportStatus;
  error?: string;
  retryable?: boolean;
  uncertain?: boolean;
}
interface Snapshot { entries: ImportEntry[]; notice: string; settled: number }

export class ImportError extends Error {
  constructor(message: string, public readonly uncertain = false) { super(message); }
}

export async function uploadDocument(file: File, canContinue: () => boolean) {
  let content = "";
  let base64: string | undefined;
  if (/\.pdf$/i.test(file.name)) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    base64 = btoa(binary);
  } else {
    content = await file.text();
  }
  // Leaving the page while File APIs are reading must not start a new POST.
  if (!canContinue()) return;
  try {
    await api.addDocument(file.name, content, base64);
  } catch (error) {
    throw new ImportError(
      error instanceof Error ? error.message : String(error),
      !(error instanceof ApiError) || error.status >= 500,
    );
  }
}

function validationError(file: File): string | undefined {
  if (!/\.(txt|md|markdown|pdf)$/i.test(file.name)) return "Chỉ hỗ trợ .txt/.md/.markdown/.pdf.";
  if (file.size > MAX_FILE_BYTES) return "File quá lớn (giới hạn 4 MiB).";
  if (file.size === 0) return "File rỗng. Hãy chọn file có nội dung.";
  if (file.name.length > 255) return "Tên file quá dài (giới hạn 255 ký tự).";
}

// One reader/POST at a time; File objects never enter storage or leave the local API.
export class ImportQueue {
  private snapshot: Snapshot = { entries: [], notice: "", settled: 0 };
  private files = new Map<number, File>();
  private listeners = new Set<() => void>();
  private nextId = 0;
  private enabled = false;
  private running = false;
  private generation = 0;

  constructor(private upload = uploadDocument) {}
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private emit(update: Partial<Snapshot>) {
    this.snapshot = { ...this.snapshot, ...update };
    this.listeners.forEach(listener => listener());
  }
  start() { this.enabled = true; void this.pump(); }
  stop() {
    this.enabled = false;
    this.generation++;
    this.files.clear();
    // No rollback: a POST already received by the server can still finish.
  }
  enqueue(files: File[]) {
    const entries = [...this.snapshot.entries];
    let duplicate = 0;
    let overflow = 0;
    for (const file of files) {
      // Metadata is not identity: distinct same-name files must never be lost.
      const activeDuplicate = entries.some(entry => {
        const active = this.files.get(entry.id);
        return (entry.status === "pending" || entry.status === "uploading") && active &&
          active === file;
      });
      if (activeDuplicate) { duplicate++; continue; }
      if (entries.length >= MAX_IMPORTS) { overflow++; continue; }
      const error = validationError(file);
      const id = ++this.nextId;
      entries.push({ id, name: file.name, size: file.size, status: error ? "failure" : "pending", error, retryable: !error });
      if (!error) this.files.set(id, file);
    }
    const notice = [
      duplicate ? `Bỏ qua ${duplicate} file trùng đang chờ hoặc đang nhập.` : "",
      overflow ? `Chưa thêm ${overflow} file: hàng đợi tối đa ${MAX_IMPORTS} file. Dọn kết quả rồi chọn lại.` : "",
    ].filter(Boolean).join(" ");
    this.emit({ entries, notice });
    void this.pump();
  }
  retry(id: number) {
    const file = this.files.get(id);
    if (!file) return;
    if (this.snapshot.entries.some(entry => entry.id !== id &&
      (entry.status === "pending" || entry.status === "uploading") && this.files.get(entry.id) === file)) {
      this.emit({ notice: "File này đang chờ hoặc đang nhập. Hãy chờ kết quả trước khi thử lại." });
      return;
    }
    this.emit({ entries: this.snapshot.entries.map(entry => entry.id === id && entry.status === "failure" && entry.retryable
      ? { ...entry, status: "pending", error: undefined, uncertain: false } : entry) });
    void this.pump();
  }
  dismiss(id: number) {
    if (this.snapshot.entries.some(entry => entry.id === id && entry.status === "uploading")) return;
    this.files.delete(id);
    this.emit({ entries: this.snapshot.entries.filter(entry => entry.id !== id) });
  }
  clearFinished() {
    for (const entry of this.snapshot.entries) {
      if (entry.status === "success" || entry.status === "failure") this.files.delete(entry.id);
    }
    this.emit({ entries: this.snapshot.entries.filter(entry => entry.status === "pending" || entry.status === "uploading"), notice: "" });
  }
  private async pump() {
    if (!this.enabled || this.running) return;
    const next = this.snapshot.entries.find(entry => entry.status === "pending");
    if (!next) return;
    const file = this.files.get(next.id)!;
    const generation = this.generation;
    const current = () => this.enabled && generation === this.generation;
    this.running = true;
    this.emit({ entries: this.snapshot.entries.map(entry => entry.id === next.id ? { ...entry, status: "uploading" } : entry) });
    let result: Partial<ImportEntry> = { status: "success" };
    try {
      await this.upload(file, current);
      this.files.delete(next.id);
    } catch (error) {
      result = { status: "failure", error: error instanceof Error ? error.message : String(error), retryable: true, uncertain: error instanceof ImportError && error.uncertain };
    } finally {
      this.running = false;
      if (current()) {
        this.emit({ entries: this.snapshot.entries.map(entry => entry.id === next.id ? { ...entry, ...result } : entry), settled: this.snapshot.settled + 1 });
        void this.pump();
      }
    }
  }
}
