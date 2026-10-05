import React, { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, ApiError, AskResp, DocEntry } from "../api";
import { deferred, textFile } from "../documents/testHelpers";
import DocsPage from "./Documents";

const doc: DocEntry = { id: "existing", name: "existing.md", size_bytes: 20, chunk_count: 1, status: "indexed", created_at: "2026-10-05" };
const response: AskResp = { answer: "Câu trả lời cũ [1]", grounded: true, citations: [{ n: 1, chunk_id: "existing:0", document: "existing.md", excerpt: "Đoạn trích cũ", offset: 0 }] };
const input = () => screen.getByLabelText("Chọn file tài liệu") as HTMLInputElement;
const choose = (...files: File[]) => fireEvent.change(input(), { target: { files } });
const ask = () => {
  fireEvent.change(screen.getByLabelText("Câu hỏi về tài liệu"), { target: { value: "Câu hỏi?" } });
  fireEvent.click(screen.getByRole("button", { name: "Hỏi" }));
};
const ready = () => screen.findByRole("button", { name: "Xoá existing.md" });

beforeEach(() => {
  vi.spyOn(api, "documents").mockResolvedValue({ documents: [doc] });
  vi.spyOn(api, "addDocument").mockResolvedValue({});
  vi.spyOn(api, "deleteDocument").mockResolvedValue({});
  vi.spyOn(api, "ask").mockResolvedValue(response);
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("shows per-file queue progress, continues after a rejection, and retries only on request", async () => {
  const first = deferred();
  vi.mocked(api.addDocument).mockReturnValueOnce(first.promise).mockRejectedValueOnce(new ApiError("PDF scan cần OCR", 400)).mockResolvedValue({});
  render(<DocsPage />);
  await ready();
  choose(textFile("one.md"), textFile("two.pdf"));
  expect(screen.getByText("Đang đọc và nhập…")).toBeTruthy();
  expect(screen.getByText("Đang chờ", { exact: true })).toBeTruthy();
  await waitFor(() => expect(api.addDocument).toHaveBeenCalledTimes(1));
  await act(async () => first.resolve({}));
  expect(await screen.findByText("PDF scan cần OCR")).toBeTruthy();
  expect(screen.getByText("Đã nhập", { exact: true })).toBeTruthy();
  expect(screen.queryByText(/Chưa xác nhận được kết quả/)).toBeNull();
  expect(api.addDocument).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole("button", { name: "Thử lại two.pdf" }));
  await waitFor(() => expect(screen.getAllByText("Đã nhập", { exact: true })).toHaveLength(2));
  expect(api.addDocument).toHaveBeenCalledTimes(3);
  fireEvent.click(screen.getByRole("button", { name: "Dọn kết quả" }));
  expect(screen.queryByRole("region", { name: "Hàng đợi nhập tài liệu" })).toBeNull();
  expect(api.deleteDocument).not.toHaveBeenCalled();
  expect(screen.getByText(doc.name)).toBeTruthy();
});

it("resets the picker and permits selecting the same file again after completion", async () => {
  render(<DocsPage />);
  await ready();
  const file = textFile();
  const value = vi.spyOn(input(), "value", "set");
  choose(file);
  expect(value).toHaveBeenCalledWith("");
  await screen.findByText("Đã nhập", { exact: true });
  choose(file);
  await waitFor(() => expect(api.addDocument).toHaveBeenCalledTimes(2));
});

it("accepts drag/drop and reports each invalid file without losing successful results", async () => {
  render(<DocsPage />);
  await ready();
  const drop = screen.getByRole("button", { name: "Chọn file .txt/.md/.pdf" }).closest(".card")!;
  fireEvent.drop(drop, { dataTransfer: { files: [textFile("bad.exe"), textFile("empty.txt", ""), textFile()] } });
  expect(await screen.findByText("Đã nhập", { exact: true })).toBeTruthy();
  expect(screen.getByText(/Chỉ hỗ trợ .txt/)).toBeTruthy();
  expect(screen.getByText(/File rỗng/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Thử lại bad.exe" })).toBeNull();
  expect(api.addDocument).toHaveBeenCalledTimes(1);
});

it("warns about an uncertain result and refreshes the list without silently resubmitting", async () => {
  vi.mocked(api.addDocument).mockRejectedValue(new TypeError("Failed to fetch"));
  render(<DocsPage />);
  await ready();
  choose(textFile());
  expect(await screen.findByText(/File có thể đã được thêm/)).toBeTruthy();
  await waitFor(() => expect(api.documents).toHaveBeenCalledTimes(2));
  expect(api.addDocument).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Tải lại danh sách" }));
  await waitFor(() => expect(api.documents).toHaveBeenCalledTimes(3));
  expect(api.addDocument).toHaveBeenCalledTimes(1);
});

it("stops queued work on navigation and refreshes existing documents when returning", async () => {
  const active = deferred();
  vi.mocked(api.addDocument).mockReturnValueOnce(active.promise);
  const view = render(<DocsPage />);
  await ready();
  choose(textFile("active.md"), textFile("pending.md"));
  await waitFor(() => expect(api.addDocument).toHaveBeenCalledTimes(1));
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
  view.unmount();
  await act(async () => active.resolve({}));
  expect(api.addDocument).toHaveBeenCalledTimes(1);
  const after = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(after);
  expect(after.defaultPrevented).toBe(false);
  render(<DocsPage />);
  await ready();
  expect(screen.queryByText("pending.md")).toBeNull();
  expect(api.documents).toHaveBeenCalledTimes(2);
});

it("keeps deletion confirmation, prevents double-delete and surfaces failures", async () => {
  const deletion = deferred();
  vi.mocked(window.confirm).mockReturnValueOnce(false).mockReturnValue(true);
  vi.mocked(api.deleteDocument).mockReturnValue(deletion.promise);
  render(<DocsPage />);
  const button = await ready();
  fireEvent.click(button);
  expect(api.deleteDocument).not.toHaveBeenCalled();
  fireEvent.click(button);
  fireEvent.click(button);
  expect(api.deleteDocument).toHaveBeenCalledTimes(1);
  expect(window.confirm).toHaveBeenCalledWith('Xoá "existing.md" và toàn bộ trích dẫn của nó?');
  await act(async () => deletion.reject(new Error("Mất kết nối")));
  expect(screen.getByRole("alert").textContent).toContain("Không xoá được");
  expect(screen.getByText("existing.md")).toBeTruthy();
});

it("shows a recoverable list error without treating it as an empty library", async () => {
  vi.mocked(api.documents).mockRejectedValueOnce(new Error("Offline"));
  render(<DocsPage />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.queryByText(/Chưa có tài liệu/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Tải lại danh sách" }));
  await ready();
  expect(screen.queryByRole("alert")).toBeNull();
});

it("ignores an older refresh that would hide a newly imported document", async () => {
  const stale = deferred<{ documents: DocEntry[] }>();
  vi.mocked(api.documents).mockReturnValueOnce(stale.promise).mockResolvedValue({ documents: [doc] });
  render(<DocsPage />);
  choose(textFile());
  await ready();
  await act(async () => stale.resolve({ documents: [] }));
  expect(screen.getByText("existing.md")).toBeTruthy();
});

it("discards an earlier answer after a document import begins", async () => {
  const oldAnswer = deferred<AskResp>();
  const importing = deferred();
  vi.mocked(api.ask).mockReturnValue(oldAnswer.promise);
  vi.mocked(api.addDocument).mockReturnValue(importing.promise);
  render(<DocsPage />);
  await ready();
  ask();
  choose(textFile());
  await act(async () => oldAnswer.resolve(response));
  expect(screen.queryByText(response.answer)).toBeNull();
  fireEvent.keyDown(screen.getByLabelText("Câu hỏi về tài liệu"), { key: "Enter" });
  expect(api.ask).toHaveBeenCalledTimes(1);
  await act(async () => importing.resolve({}));
});

it("clears answer and expanded citations after deletion and resets expansion for a new answer", async () => {
  render(<DocsPage />);
  await ready();
  ask();
  fireEvent.click(await screen.findByRole("button", { name: "[1] existing.md" }));
  expect(screen.getByText("Đoạn trích cũ")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Xoá existing.md" }));
  expect(screen.queryByText("Đoạn trích cũ")).toBeNull();
  await waitFor(() => expect(api.documents).toHaveBeenCalledTimes(2));
  await waitFor(() => expect((screen.getByRole("button", { name: "Hỏi" }) as HTMLButtonElement).disabled).toBe(false));
  ask();
  await screen.findByRole("button", { name: "[1] existing.md" });
  expect(screen.queryByText("Đoạn trích cũ")).toBeNull();
});

it("handles StrictMode effect replay without duplicate imports or stale initial refreshes", async () => {
  render(<StrictMode><DocsPage /></StrictMode>);
  await ready();
  choose(textFile());
  await screen.findByText("Đã nhập", { exact: true });
  expect(api.addDocument).toHaveBeenCalledTimes(1);
});

it("keeps a confirmed import successful even if its follow-up list refresh fails", async () => {
  vi.mocked(api.documents).mockResolvedValueOnce({ documents: [doc] }).mockRejectedValueOnce(new Error("Offline"));
  render(<DocsPage />);
  await ready();
  choose(textFile());
  await screen.findByText("Đã nhập", { exact: true });
  await screen.findByRole("alert");
  expect(screen.getByText("existing.md")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Thử lại notes.md" })).toBeNull();
  expect(api.addDocument).toHaveBeenCalledTimes(1);
});

it("ignores an older answer after confirmed deletion, even if its response arrives late", async () => {
  const oldAnswer = deferred<AskResp>();
  vi.mocked(api.ask).mockReturnValue(oldAnswer.promise);
  render(<DocsPage />);
  await ready();
  ask();
  vi.mocked(api.documents).mockResolvedValue({ documents: [] });
  fireEvent.click(screen.getByRole("button", { name: "Xoá existing.md" }));
  await screen.findByText(/Chưa có tài liệu/);
  await act(async () => oldAnswer.resolve(response));
  expect(screen.queryByText(response.answer)).toBeNull();
  expect(screen.queryByRole("button", { name: "[1] existing.md" })).toBeNull();
});

it("displays read failures on the correct file and allows a manual retry", async () => {
  const file = textFile();
  const read = vi.fn().mockRejectedValueOnce(new Error("Không đọc được file")).mockResolvedValue("Nội dung");
  Object.defineProperty(file, "text", { value: read });
  render(<DocsPage />);
  await ready();
  choose(file);
  await screen.findByText("Không đọc được file");
  expect(api.addDocument).not.toHaveBeenCalled();
  expect(screen.queryByText(/File có thể đã được thêm/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Thử lại notes.md" }));
  await screen.findByText("Đã nhập", { exact: true });
  expect(api.addDocument).toHaveBeenCalledTimes(1);
});
