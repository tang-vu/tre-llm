import { afterEach, expect, it, vi } from "vitest";
import { ChatSession } from "./chatSession";
import { conversations, history, json, network, settle } from "./chat/testHelpers";

afterEach(() => vi.unstubAllGlobals());
it("keeps only the latest same-conversation history response", async () => {
  const session = new ChatSession(); const net = network();
  void session.refreshConversations(); await net.list(); session.select("A");
  void session.loadHistory(); await net.load("A", history(["assistant", "Fresh"]), 1);
  await net.load("A", history(["assistant", "Stale"]), 0);
  const c = session.getSnapshot().retained.find(c => c.id === "A")!;
  expect(c.messages.map(m => m.content)).toEqual(["Fresh"]);
});
it("ignores a delayed history read after its conversation has been deleted", async () => {
  const session = new ChatSession(); const net = network();
  void session.refreshConversations(); await net.list(); session.select("A");
  void session.deleteConversation("A"); await settle(() => net.deletions[0].response.resolve(json({ deleted: "A" })));
  await net.list(1, [conversations[1]]); await net.load("A", history(["assistant", "Stale"]));
  expect(session.getSnapshot().retained.some(c => c.id === "A")).toBe(false);
});

it.each(["eof", "error"])("refreshes a withheld initial list after %s before the conv event without losing the prompt", async ending => {
  const session = new ChatSession(); const net = network();
  void session.refreshConversations(); void session.send("Unconfirmed prompt"); await settle();
  const created = { ...conversations[0], id: "created", title: "Created before event" };
  await net.list(0, [created]); expect(session.getSnapshot().conversations).toEqual([]);
  if (ending === "error") await net.wires[0].event({ type: "error", error: "Rejected" });
  await net.wires[0].close(); await net.list(1, [created]);
  expect(session.getSnapshot().conversations).toEqual([created]); expect(session.canSend()).toBe(false);
  expect(session.getSnapshot().retained[0].messages[0].content).toBe("Unconfirmed prompt");
});

it("ignores an initial list response arriving after binding and the newer refresh", async () => {
  const session = new ChatSession(); const net = network();
  void session.refreshConversations(); void session.send("Prompt"); await settle();
  const owner = session.getSnapshot().selected;
  await net.wires[0].event({ type: "conv", id: "created" });
  const created = { ...conversations[0], id: "created", title: "Created before event" };
  await net.list(1, [created]); await net.list(0, []);
  session.select("created"); expect(session.getSnapshot().selected).toBe(owner); expect(net.histories.has("created")).toBe(false);
  await net.wires[0].close();
});
