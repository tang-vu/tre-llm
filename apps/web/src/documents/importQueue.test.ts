import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import { ImportError, ImportQueue, MAX_FILE_BYTES, MAX_IMPORTS, uploadDocument } from "./importQueue";
import { deferred, textFile } from "./testHelpers";

afterEach(() => vi.restoreAllMocks());

describe("local import queue (protocol only)", () => {
  it("serializes reads/uploads in selection order and keeps a failed file retryable", async () => {
    const first = deferred();
    const upload = vi.fn().mockReturnValueOnce(first.promise).mockRejectedValueOnce(new Error("Lỗi đọc file")).mockResolvedValue(undefined);
    const queue = new ImportQueue(upload);
    queue.start();
    queue.enqueue([textFile("a.md"), textFile("b.md"), textFile("c.md")]);
    expect(upload).toHaveBeenCalledTimes(1);
    expect(queue.getSnapshot().entries.map(e => e.status)).toEqual(["uploading", "pending", "pending"]);
    first.resolve(undefined);
    await vi.waitFor(() => expect(queue.getSnapshot().entries.map(e => e.status)).toEqual(["success", "failure", "success"]));
    queue.retry(2);
    queue.retry(2);
    await vi.waitFor(() => expect(queue.getSnapshot().entries.every(e => e.status === "success")).toBe(true));
    expect(upload.mock.calls.map(([file]) => file.name)).toEqual(["a.md", "b.md", "c.md", "b.md"]);
  });

  it("reports every invalid file without starting a read or request", () => {
    const upload = vi.fn();
    const queue = new ImportQueue(upload);
    queue.start();
    const large = textFile("large.txt");
    Object.defineProperty(large, "size", { value: MAX_FILE_BYTES + 1 });
    queue.enqueue([textFile("bad.exe"), textFile("empty.txt", ""), large, textFile("x".repeat(256) + ".md")]);
    expect(queue.getSnapshot().entries).toHaveLength(4);
    expect(queue.getSnapshot().entries.every(e => e.status === "failure" && !e.retryable && e.error)).toBe(true);
    queue.retry(1);
    expect(upload).not.toHaveBeenCalled();
  });

  it("bounds retained files and supports pending removal and clear finished", async () => {
    const first = deferred();
    const upload = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(undefined);
    const queue = new ImportQueue(upload);
    queue.start();
    queue.enqueue(Array.from({ length: MAX_IMPORTS + 3 }, (_, i) => textFile(`${i}.md`)));
    expect(queue.getSnapshot().entries).toHaveLength(MAX_IMPORTS);
    expect(queue.getSnapshot().notice).toContain("Chưa thêm 3 file");
    queue.dismiss(1); // Active work cannot be silently cancelled.
    queue.dismiss(2);
    expect(queue.getSnapshot().entries).toHaveLength(MAX_IMPORTS - 1);
    first.resolve(undefined);
    await vi.waitFor(() => expect(queue.getSnapshot().entries.every(e => e.status === "success")).toBe(true));
    expect(upload.mock.calls.map(([file]) => file.name)).not.toContain("1.md");
    queue.clearFinished();
    expect(queue.getSnapshot().entries).toEqual([]);
    queue.enqueue([textFile("next.md")]);
    await vi.waitFor(() => expect(queue.getSnapshot().entries[0].status).toBe("success"));
  });

  it("suppresses only matching active selections, preserving legitimate same-name documents", async () => {
    const first = deferred();
    const upload = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(undefined);
    const queue = new ImportQueue(upload);
    queue.start();
    const file = textFile();
    queue.enqueue([file, file, textFile()]); // Identical metadata, distinct File: preserve it.
    queue.enqueue([file]);
    expect(queue.getSnapshot().entries).toHaveLength(2);
    expect(queue.getSnapshot().notice).toContain("file trùng");
    first.resolve(undefined);
    await vi.waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    queue.enqueue([textFile()]); // A deliberate selection after completion is allowed.
    await vi.waitFor(() => expect(upload).toHaveBeenCalledTimes(3));
  });

  it("does not retry a failed entry while the same File object is active again", async () => {
    const active = deferred();
    const upload = vi.fn().mockRejectedValueOnce(new Error("Lỗi")).mockReturnValue(active.promise);
    const queue = new ImportQueue(upload);
    queue.start();
    const file = textFile();
    queue.enqueue([file]);
    await vi.waitFor(() => expect(queue.getSnapshot().entries[0].status).toBe("failure"));
    queue.enqueue([file]);
    queue.retry(1);
    expect(queue.getSnapshot().entries.map(e => e.status)).toEqual(["failure", "uploading"]);
    expect(queue.getSnapshot().notice).toContain("Hãy chờ kết quả");
    queue.stop();
    active.resolve(undefined);
  });

  it("does not launch remaining imports after the page unmounts", async () => {
    const active = deferred();
    const upload = vi.fn().mockReturnValue(active.promise);
    const queue = new ImportQueue(upload);
    queue.start();
    queue.enqueue([textFile("a.md"), textFile("b.md")]);
    queue.stop();
    active.resolve(undefined);
    await active.promise;
    expect(upload).toHaveBeenCalledTimes(1);
  });

  it("does not start a POST if the page is left while reading a file", async () => {
    const read = deferred<string>();
    const file = textFile();
    Object.defineProperty(file, "text", { value: () => read.promise });
    const post = vi.spyOn(api, "addDocument");
    const queue = new ImportQueue();
    queue.start();
    queue.enqueue([file]);
    queue.stop();
    read.resolve("Đọc xong");
    await read.promise;
    expect(post).not.toHaveBeenCalled();
  });

  it("uses UTF-8 text and base64 PDF contracts without external URLs", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("{}", { status: 200 }));
    await uploadDocument(textFile(), () => true);
    await uploadDocument(textFile("a.PDF", "%PDF-1.4"), () => true);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/documents", "/api/documents"]);
    const bodies = fetchMock.mock.calls.map(([, options]) => JSON.parse(options!.body as string));
    expect(bodies).toEqual([{ name: "notes.md", content: "Ghi chú tiếng Việt" }, { name: "a.PDF", content_base64: btoa("%PDF-1.4") }]);
  });

  it.each([
    [new ApiError("PDF scan cần OCR", 400), false],
    [new ApiError("Server error", 500), true],
    [new TypeError("Failed to fetch"), true],
  ])("distinguishes rejected and uncertain request outcomes: %s", async (error, uncertain) => {
    vi.spyOn(api, "addDocument").mockRejectedValue(error);
    await expect(uploadDocument(textFile(), () => true)).rejects.toMatchObject({ message: error.message, uncertain });
  });

  it("never automatically retries an uncertain result", async () => {
    const upload = vi.fn().mockRejectedValue(new ImportError("Mất kết nối", true));
    const queue = new ImportQueue(upload);
    queue.start();
    queue.enqueue([textFile()]);
    await vi.waitFor(() => expect(queue.getSnapshot().entries[0]).toMatchObject({ status: "failure", uncertain: true }));
    expect(upload).toHaveBeenCalledTimes(1);
  });
});
