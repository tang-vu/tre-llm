import React, { StrictMode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ChatPage from "./Chat";
import { ChatSession } from "../chatSession";
import { conversations, history, json, network, settle, Wire } from "../chat/testHelpers";

let session: ChatSession;
let net: ReturnType<typeof network>;
const input = () => screen.getByLabelText("Tin nhắn") as HTMLTextAreaElement;
const type = (text: string) => fireEvent.change(input(), { target: { value: text } });
const click = (name: string) => fireEvent.click(screen.getByRole("button", { name }));
const rows = () => [...document.querySelectorAll(".msg")].map(el => ({ role: el.classList.contains("user") ? "user" : "assistant", content: el.querySelector(".markdown")?.textContent ?? el.querySelector("p")?.textContent ?? "" }));
const contents = () => session.getSnapshot().retained.find(c => c.key === session.getSnapshot().selected)!.messages.map(m => m.content);
async function start(strict = false) {
  const page = <ChatPage session={session} />;
  const view = render(strict ? <StrictMode>{page}</StrictMode> : page);
  await net.list(net.lists.length - 1);
  return view;
}
async function select(id: string, messages = history()) { click(`Conversation ${id}`); await net.load(id, messages); }
async function send(text: string): Promise<Wire> { type(text); click("Gửi"); await settle(); return net.wires[net.wires.length - 1]; }
async function done(wire: Wire, finish_reason = "stop") { await wire.event({ type: "done", finish_reason }); await wire.end(); }

beforeEach(() => {
  session = new ChatSession(); net = network();
  Object.defineProperty(HTMLElement.prototype, "scrollTo", { configurable: true, value: vi.fn() });
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(async () => {
  cleanup();
  for (const wire of net.wires) if (!wire.ended) await wire.close();
  for (const response of net.cancellations) response.resolve(json({ cancelled: 1 }));
  await settle(); vi.unstubAllGlobals(); vi.restoreAllMocks();
});

it("keeps the first prompt and answer when conv arrives before tokens without fetching incomplete history", async () => {
  await start(); const wire = await send("Câu hỏi đầu tiên");
  await wire.event({ type: "conv", id: "created" });
  expect(net.histories.size).toBe(0);
  await wire.event({ type: "token", text: "Câu trả lời" }); await done(wire);
  expect(contents()).toEqual(["Câu hỏi đầu tiên", "Câu trả lời"]);
  expect(document.querySelector(".msg.user")?.textContent).toBe("Câu hỏi đầu tiên");
  expect(screen.getByText("Câu trả lời")).toBeTruthy();
  expect(screen.getByText(/Đã hoàn tất và lưu/)).toBeTruthy();
  const next = await send("Tiếp tục"); expect(next.body.conversation_id).toBe("created");
});

it("ignores older A history when B is selected and retains per-conversation drafts", async () => {
  await start(); click("Conversation A"); type("Bản nháp A"); click("Conversation B"); type("Bản nháp B");
  await net.load("B", history(["user", "B question"], ["assistant", "B saved"]));
  await net.load("A", history(["user", "A question"]));
  expect(contents()).toEqual(["B question", "B saved"]); expect(input().value).toBe("Bản nháp B");
  click("Conversation A"); expect(contents()).toEqual(["A question"]); expect(input().value).toBe("Bản nháp A");
});

it("blocks clicks, examples and Enter while history loads or fails and permits explicit read retry with a draft", async () => {
  await start(); click("Conversation A"); type("Giữ bản nháp"); click("Gửi"); fireEvent.keyDown(input(), { key: "Enter" });
  expect(net.wires).toHaveLength(0); expect(screen.queryByText("Bắt đầu bằng một ví dụ:")).toBeNull();
  await settle(() => net.histories.get("A")![0].reject(new Error("Offline")));
  expect(screen.getByRole("alert").textContent).toContain("Offline"); click("Gửi"); expect(net.wires).toHaveLength(0);
  click("Tải lại lịch sử"); await net.load("A", history(["assistant", "Ngữ cảnh cũ"]), 1);
  expect(input().value).toBe("Giữ bản nháp"); click("Gửi"); await settle();
  expect(net.wires[0].body).toMatchObject({ conversation_id: "A", message: "Giữ bản nháp" });
  expect(contents()).toEqual(["Ngữ cảnh cũ", "Giữ bản nháp", ""]);
});

it("keeps tokens in A when navigating to B and restores A’s active owner", async () => {
  await start(); await select("A"); const wire = await send("A question"); await wire.event({ type: "conv", id: "A" });
  await select("B", history(["user", "B question"], ["assistant", "B saved"]));
  await wire.event({ type: "token", text: "A streamed" });
  expect(contents()).toEqual(["B question", "B saved"]);
  click("Về cuộc trò chuyện đang chạy"); expect(contents()).toEqual(["A question", "A streamed"]);
  expect((screen.getByRole("button", { name: "Xoá Conversation A" }) as HTMLButtonElement).disabled).toBe(true);
});

it("does not rebind New to a late old conv event and keeps the old partial reachable", async () => {
  await start(); const old = await send("Old prompt"); click("+ Cuộc trò chuyện mới"); type("New draft");
  await old.event({ type: "conv", id: "old" }); await old.event({ type: "token", text: "Old answer" }); await done(old);
  expect(contents()).toEqual([]); expect(input().value).toBe("New draft");
  click("Gửi"); await settle(); expect(net.wires[1].body.conversation_id).toBe("");
  click("Old prompt (phiên này)"); expect(contents()).toEqual(["Old prompt", "Old answer"]);
});

it.each(["cancel", "stream"])("keeps the stop barrier until both responses settle, %s first", async first => {
  await start(); const old = await send("Old prompt"); await old.event({ type: "conv", id: "old" });
  await old.event({ type: "token", text: "Partial" }); click("Dừng"); click("Dừng");
  expect(net.cancellations).toHaveLength(1);
  expect(contents()).toEqual(["Old prompt", "Partial"]);
  click("+ Cuộc trò chuyện mới"); type("New request");
  if (first === "cancel") await settle(() => net.cancellations[0].resolve(json({ cancelled: 1 })));
  else await done(old, "cancelled");
  fireEvent.keyDown(input(), { key: "Enter" }); expect(net.wires).toHaveLength(1);
  expect(screen.queryByRole("button", { name: "Gửi" })).toBeNull();
  if (first === "cancel") await done(old, "cancelled");
  else await settle(() => net.cancellations[0].resolve(json({ cancelled: 1 })));
  click("Gửi"); await settle(); expect(net.wires).toHaveLength(2); expect(screen.getByRole("button", { name: "Dừng" })).toBeTruthy();
});

it("waits for HTTP EOF after [DONE] and preserves an early Stop that the server did not honour honestly", async () => {
  await start(); const wire = await send("Prompt"); click("Dừng");
  await settle(() => net.cancellations[0].resolve(json({ cancelled: 0 })));
  await wire.event({ type: "conv", id: "created" }); await wire.event({ type: "token", text: "Full answer" });
  await wire.event({ type: "done", finish_reason: "stop" }); await wire.raw("data: [DONE]\n\n");
  expect(session.canSend()).toBe(false); expect(screen.queryByText(/Đã dừng;/)).toBeNull();
  await wire.close(); expect(session.canSend()).toBe(true); expect(screen.getByText(/Đã hoàn tất và lưu/)).toBeTruthy();
});

it("retains a cancel failure and waits for stream completion without retrying global cancellation", async () => {
  await start(); const wire = await send("Prompt"); click("Dừng");
  await settle(() => net.cancellations[0].reject(new Error("Offline")));
  expect(screen.getByRole("alert").textContent).toContain("Chưa xác nhận lệnh dừng");
  expect(session.canSend()).toBe(false); click("Dừng"); expect(net.cancellations).toHaveLength(1);
  await wire.event({ type: "conv", id: "created" }); await done(wire); expect(session.canSend()).toBe(true);
});

it("retains active ownership and typed text across route remounts and StrictMode effect replay", async () => {
  const view = await start(true); const wire = await send("Prompt"); type("Next draft");
  view.unmount(); await wire.event({ type: "conv", id: "created" }); await wire.event({ type: "token", text: "While away" });
  await start(true); expect(contents()).toEqual(["Prompt", "While away"]); expect(input().value).toBe("Next draft");
  expect(screen.getByRole("button", { name: "Dừng" })).toBeTruthy(); expect(net.cancellations).toHaveLength(0); expect(net.wires).toHaveLength(1);
});

it.each(["error", "disconnect", "eof"])("retains partial text and reasoning after %s, without claiming persistence or resubmitting", async ending => {
  await start(); const wire = await send("Prompt"); await wire.event({ type: "conv", id: "created" });
  await wire.event({ type: "reasoning", text: "Thinking" }); await wire.event({ type: "token", text: "Useful partial" });
  if (ending === "error") { await wire.event({ type: "error", error: "Server error" }); await wire.end(); }
  else if (ending === "disconnect") await wire.fail(); else await wire.close();
  expect(contents()).toEqual(["Prompt", "Useful partial"]); expect(screen.getByText("Thinking")).toBeTruthy();
  expect(screen.getByText("Chưa xác nhận lưu; chỉ giữ trong phiên này.")).toBeTruthy();
  expect(screen.queryByText(/Đã hoàn tất/)).toBeNull(); expect(net.wires).toHaveLength(1);
  click("+ Cuộc trò chuyện mới"); click("Prompt (phiên này)"); expect(contents()).toEqual(["Prompt", "Useful partial"]);
});

it("keeps the submitted prompt after HTTP failure or empty termination", async () => {
  await start(); const wire = await send("Recover this prompt"); await wire.close();
  expect(contents()).toEqual(["Recover this prompt", ""]); expect(screen.getByRole("alert").textContent).toContain("chưa xác nhận");
  expect(session.hasUnsavedWork()).toBe(true); expect(net.wires).toHaveLength(1);
});

it("blocks duplicate sends and Vietnamese IME Enter without blocking a later ordinary Enter", async () => {
  await start(); type("Tiếng Việt");
  fireEvent.compositionStart(input()); fireEvent.keyDown(input(), { key: "Enter" }); fireEvent.compositionEnd(input());
  fireEvent.keyDown(input(), { key: "Enter", isComposing: true }); fireEvent.keyDown(input(), { key: "Enter", keyCode: 229 });
  fireEvent.keyDown(input(), { key: "Enter", shiftKey: true }); expect(net.wires).toHaveLength(0);
  fireEvent.keyDown(input(), { key: "Enter" }); fireEvent.keyDown(input(), { key: "Enter" });
  await settle(); expect(net.wires).toHaveLength(1);
});

it("does not discard an entered draft when submitting an example", async () => {
  await start(); type("Keep this draft"); click("Hướng dẫn mình cách gỡ lỗi tốt"); await settle();
  expect(input().value).toBe("Keep this draft"); expect(net.wires[0].body.message).toBe("Hướng dẫn mình cách gỡ lỗi tốt");
});

it("confirms deletion, rejects repeats, and preserves history on failure", async () => {
  await start(); await select("A", history(["assistant", "A saved"]));
  vi.mocked(window.confirm).mockReturnValueOnce(false); click("Xoá Conversation A"); expect(net.deletions).toHaveLength(0);
  click("Xoá Conversation A"); click("Xoá Conversation A"); expect(net.deletions).toHaveLength(1);
  type("Draft during delete"); click("Gửi"); expect(net.wires).toHaveLength(0);
  await settle(() => net.deletions[0].response.resolve(json({ detail: "Synthetic failure" }, 500)));
  expect(contents()).toEqual(["A saved"]); expect(input().value).toBe("Draft during delete");
  expect(screen.getAllByRole("alert").map(e => e.textContent).join(" ")).toContain("Synthetic failure");
});

it("does not delete an active persistence target, and ignores a pre-delete list response", async () => {
  await start(); await select("A"); const wire = await send("Prompt"); await wire.event({ type: "conv", id: "A" });
  click("Xoá Conversation A"); expect(net.deletions).toHaveLength(0); await done(wire);
  click("Tải lại danh sách"); const stale = net.lists.length - 1;
  click("Xoá Conversation A"); await settle(() => net.deletions[0].response.resolve(json({ deleted: "A" })));
  await net.list(net.lists.length - 1, [conversations[1]]); await net.list(stale);
  expect(screen.queryByRole("button", { name: "Conversation A" })).toBeNull(); expect(contents()).toEqual([]);
});

it("reloads the same ID without losing drafts or allowing sends into unknown history", async () => {
  await start(); await select("A", history(["assistant", "Old"])); type("Draft");
  click("Tải lại lịch sử"); click("Conversation A"); click("Gửi"); expect(net.wires).toHaveLength(0);
  await net.load("A", history(["assistant", "Fresh"]), 1); expect(contents()).toEqual(["Fresh"]); expect(input().value).toBe("Draft");
  expect(rows()[0].role).toBe("assistant");
});

it.each(["done", "error"])("retires Stop at the %s event while retaining the HTTP EOF send barrier", async terminal => {
  await start(); const wire = await send("Prompt"); await wire.event({ type: "conv", id: "created" });
  if (terminal === "done") await wire.event({ type: "done", finish_reason: "stop" });
  else await wire.event({ type: "error", error: "Error" });
  click("Dừng"); expect(net.cancellations).toHaveLength(0); expect(session.canSend()).toBe(false);
  await wire.end(); expect(session.canSend()).toBe(terminal === "done");
});

it("keeps a delayed cancellation failure with its original conversation", async () => {
  await start(); await select("A"); const wire = await send("A prompt"); click("Dừng");
  await select("B", history(["assistant", "B saved"]));
  await settle(() => net.cancellations[0].reject(new Error("Cancel failure")));
  expect(screen.queryByRole("alert")).toBeNull(); expect(contents()).toEqual(["B saved"]);
  click("Về cuộc trò chuyện đang chạy"); expect(screen.getByRole("alert").textContent).toContain("Cancel failure");
  await done(wire);
});

it("loads history after interruption while preserving unconfirmed copies separately and never resends them", async () => {
  await start(); const wire = await send("Prompt"); await wire.event({ type: "conv", id: "created" });
  await wire.event({ type: "token", text: "Partial" }); await wire.fail(); type("Next draft");
  click("Tải lại lịch sử"); await net.load("created", history(["user", "Prompt"]));
  expect(contents()).toEqual(["Prompt"]); expect(screen.getByRole("region", { name: "Bản giữ trong phiên này" }).textContent).toContain("Partial");
  expect(input().value).toBe("Next draft");
  click("Tải lại lịch sử"); await net.load("created", history(["user", "Prompt"]), 1);
  expect(screen.getAllByText("Partial")).toHaveLength(1); expect(net.wires).toHaveLength(1);
  vi.mocked(window.confirm).mockReturnValueOnce(false); click("Bỏ bản nháp trong phiên"); expect(screen.getByText("Partial")).toBeTruthy();
  click("Bỏ bản nháp trong phiên"); expect(screen.queryByText("Partial")).toBeNull(); expect(contents()).toEqual(["Prompt"]);
  expect(net.deletions).toHaveLength(0); expect(input().value).toBe("");
});

it("preserves a new draft across list failure and ignores a stale StrictMode list response", async () => {
  await start(true); type("Keep");
  await net.list(0, []); expect(screen.getByRole("button", { name: "Conversation A" })).toBeTruthy();
  click("Tải lại danh sách"); await settle(() => net.lists[2].reject(new Error("List offline")));
  expect(screen.getByRole("alert").textContent).toContain("List offline"); expect(input().value).toBe("Keep");
  click("Tải lại danh sách"); await net.list(3); expect(screen.queryByRole("alert")).toBeNull();
});

it("bounds retained drafts without evicting unsaved text and can free a slot explicitly", async () => {
  await start();
  for (let i = 0; i < 20; i++) { type(`Draft ${i}`); click("+ Cuộc trò chuyện mới"); }
  expect(session.getSnapshot().retained).toHaveLength(20); expect(input().value).toBe("Draft 19");
  expect(screen.getByRole("alert").textContent).toContain("20 cuộc trò chuyện");
  click("Bỏ bản nháp trong phiên"); expect(input().value).toBe("");
  click("Draft 0 (phiên này)"); expect(input().value).toBe("Draft 0");
  click("+ Cuộc trò chuyện mới"); expect(input().value).toBe(""); expect(session.getSnapshot().retained).toHaveLength(20);
});

it("does not lose a newer selection while a different conversation deletion finishes", async () => {
  await start(); await select("A", history(["assistant", "A saved"])); click("Xoá Conversation A");
  await select("B", history(["assistant", "B saved"])); type("B draft");
  await settle(() => net.deletions[0].response.resolve(json({ deleted: "A" })));
  expect(contents()).toEqual(["B saved"]); expect(input().value).toBe("B draft");
});

it("shows HTTP errors while keeping the submitted text without automatic retry", async () => {
  await start(); net.fetch.mockImplementationOnce(async () => json({ detail: "Unavailable" }, 503));
  type("Keep failed prompt"); click("Gửi"); await settle();
  expect(contents()).toEqual(["Keep failed prompt", ""]); expect(screen.getByRole("alert").textContent).toContain("HTTP 503");
  expect(net.wires).toHaveLength(0);
});


it("requires history reconciliation before sending after an unconfirmed turn", async () => {
  await start(); await select("A"); const wire = await send("First prompt");
  await wire.event({ type: "conv", id: "A" }); await wire.event({ type: "token", text: "Unconfirmed partial" }); await wire.fail();
  type("Next prompt"); click("Gửi"); fireEvent.keyDown(input(), { key: "Enter" }); expect(net.wires).toHaveLength(1);
  click("Tải lại lịch sử"); await net.load("A", history(["user", "First prompt"]), 1);
  click("Gửi"); await settle(); expect(net.wires[1].body).toEqual({ conversation_id: "A", message: "Next prompt", enable_thinking: false });
  expect(screen.getByRole("region", { name: "Bản giữ trong phiên này" }).textContent).toContain("Không tự gửi lại hoặc dùng làm ngữ cảnh");
});


it("reconciles an uncertain committed deletion before another send can recreate its ID", async () => {
  await start(); await select("A", history(["user", "Deleted question"], ["assistant", "Deleted answer"]));
  click("Xoá Conversation A"); await settle(() => net.deletions[0].response.reject(new TypeError("Lost DELETE response")));
  type("Next question"); click("Gửi"); expect(net.wires).toHaveLength(0);
  click("Tải lại lịch sử"); await net.load("A", history(), 1);
  expect(contents()).toEqual([]); expect(input().value).toBe("Next question"); click("Gửi"); await settle();
  expect(net.wires).toHaveLength(1); expect(contents()).toEqual(["Next question", ""]); expect(net.deletions).toHaveLength(1);
});


it("preserves composer text entered while a successful deletion was pending", async () => {
  await start(); await select("A", history(["assistant", "A saved"])); click("Xoá Conversation A");
  type("New draft after confirmation"); await settle(() => net.deletions[0].response.resolve(json({ deleted: "A" })));
  expect(input().value).toBe("New draft after confirmation"); expect(contents()).toEqual([]);
  click("Gửi"); await settle(); expect(net.wires[0].body.conversation_id).toBe("");
});


it("distinguishes an empty saved response and a length-limited saved response from interruption", async () => {
  await start(); const empty = await send("Prompt"); await empty.event({ type: "conv", id: "created" }); await done(empty);
  expect(screen.getByText(/Chưa nhận được nội dung trả lời/)).toBeTruthy(); expect(screen.queryByRole("alert")).toBeNull();
  const limited = await send("Next"); await limited.event({ type: "conv", id: "created" });
  await limited.event({ type: "token", text: "Limited answer" }); await done(limited, "length");
  expect(screen.getByText(/Đã đạt giới hạn độ dài/)).toBeTruthy(); expect(screen.queryByText(/Chưa xác nhận lưu;/)).toBeNull();
});


it.each(['"bad"', '1e999', 'null', '-2'])("ignores invalid optional timing %s without misreporting a saved response", async speed => {
  await start(); const wire = await send("Prompt"); await wire.event({ type: "conv", id: "created" });
  await wire.raw(`data: {"type":"done","finish_reason":"stop","timings":{"predicted_per_second":${speed}}}\n\n`); await wire.end();
  expect(screen.queryByRole("alert")).toBeNull(); expect(screen.getByText(/Đã hoàn tất và lưu/)).toBeTruthy();
});


it("does not expose a newly created ID as a second view before its conv event binds the owner", async () => {
  await start(); const wire = await send("Prompt"); const owner = session.getSnapshot().selected;
  click("Tải lại danh sách");
  const created = { ...conversations[0], id: "created", title: "New server conversation" };
  await net.list(net.lists.length - 1, [created, ...conversations]);
  expect(screen.queryByRole("button", { name: "New server conversation" })).toBeNull();
  await wire.event({ type: "conv", id: "created" }); await net.list(net.lists.length - 1, [created, ...conversations]);
  click("New server conversation"); expect(session.getSnapshot().selected).toBe(owner); expect(net.histories.has("created")).toBe(false);
  await wire.event({ type: "token", text: "Owned answer" }); expect(contents()).toEqual(["Prompt", "Owned answer"]);
});


it("blocks deletions until a new request’s persistence target is known", async () => {
  await start(); const wire = await send("Prompt");
  click("Xoá Conversation A"); await settle(() => { void session.deleteConversation("not-yet-bound"); session.select("not-yet-bound"); }); expect(net.deletions).toHaveLength(0);
  expect(net.histories.has("not-yet-bound")).toBe(false);
  await wire.event({ type: "conv", id: "created" });
  click("Xoá Conversation A"); expect(net.deletions).toHaveLength(1);
  await settle(() => net.deletions[0].response.resolve(json({ deleted: "A" })));
  await wire.event({ type: "token", text: "Preserved" }); expect(contents()).toEqual(["Prompt", "Preserved"]);
});

it("does not retain a false waiting notice when cancellation fails after the stream finishes", async () => {
  await start(); const wire = await send("Prompt"); click("Dừng");
  await wire.event({ type: "conv", id: "created" }); await done(wire);
  await settle(() => net.cancellations[0].reject(new Error("Cancel response lost")));
  expect(screen.getByRole("alert").textContent).toContain("Chưa xác nhận lệnh dừng");
  expect(screen.queryByText(/Vẫn chờ/)).toBeNull(); expect(screen.getByRole("button", { name: "Gửi" })).toBeTruthy();
});

it("ignores a pre-conv list response that arrives after binding while keeping the active view unique", async () => {
  await start(); const wire = await send("Prompt"); const owner = session.getSnapshot().selected;
  click("Tải lại danh sách"); const stale = net.lists.length - 1;
  await wire.event({ type: "conv", id: "created" });
  const created = { ...conversations[0], id: "created", title: "New server conversation" };
  await net.list(net.lists.length - 1, [created, ...conversations]); await net.list(stale, []);
  click("New server conversation"); expect(session.getSnapshot().selected).toBe(owner);
  expect(session.getSnapshot().retained.filter(c => c.id === "created")).toHaveLength(1);
});

it("holds a remount list update before conv without losing another conversation’s draft", async () => {
  const view = await start(); await select("A"); type("Keep A draft"); click("+ Cuộc trò chuyện mới");
  const wire = await send("New prompt"); view.unmount(); render(<ChatPage session={session} />);
  const created = { ...conversations[0], id: "created", title: "New server conversation" };
  await net.list(net.lists.length - 1, [created, ...conversations]);
  expect(screen.queryByRole("button", { name: "New server conversation" })).toBeNull();
  click("Conversation A"); expect(input().value).toBe("");
  expect(screen.getByText(/Đang mở cuộc trò chuyện/)).toBeTruthy();
  await wire.event({ type: "conv", id: "created" }); await net.list(net.lists.length - 1, [created, ...conversations]);
  await wire.event({ type: "token", text: "New answer" }); click("New server conversation");
  expect(contents()).toEqual(["New prompt", "New answer"]);
  click("Conversation A"); expect(input().value).toBe("Keep A draft");
});
