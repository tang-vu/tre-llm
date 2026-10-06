import { afterEach, expect, it, vi } from "vitest";
import { streamChat } from "./api";

afterEach(() => vi.unstubAllGlobals());
it("parses split UTF-8 chunks and releases the reader after draining past the terminal marker", async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start(c) { controller = c; } });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
  const events: unknown[] = [];
  let settled = false;
  const run = (async () => { for await (const ev of streamChat({ message: "Prompt" })) events.push(ev); settled = true; })();
  const bytes = new TextEncoder().encode('data: {"type":"token","text":"Tiếng Việt"}\n\ndata: {"type":"done","finish_reason":"stop"}\n\ndata: [DONE]\n\n');
  for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
  for (let i = 0; i < bytes.length * 3; i++) await Promise.resolve();
  expect(events).toEqual([{ type: "token", text: "Tiếng Việt" }, { type: "done", finish_reason: "stop" }]);
  expect(settled).toBe(false); expect(body.locked).toBe(true);
  controller.enqueue(new TextEncoder().encode('data: {"type":"token","text":"Ignored after marker"}\n\n'));
  controller.close(); await run; expect(body.locked).toBe(false); expect(events).toHaveLength(2);
});
it("releases the reader after a transport error without hiding the failure", async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start(c) { controller = c; } });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
  const iterator = streamChat({ message: "Prompt" }); const next = iterator.next();
  controller.error(new TypeError("Disconnected"));
  await expect(next).rejects.toThrow("Disconnected"); expect(body.locked).toBe(false);
});
