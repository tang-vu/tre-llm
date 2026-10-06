// Synthetic HTTP/SSE fixtures exercise the production parser, not model inference.
import { act } from "@testing-library/react";
import { vi } from "vitest";
import { ChatEvent, ConvMsg } from "../api";
import { deferred } from "../documents/testHelpers";

export const conversations = ["A", "B"].map(id => ({ id, title: `Conversation ${id}`, model_id: "synthetic", created_at: "2026-10-06", updated_at: "2026-10-06" }));
export const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
export const history = (...pairs: [string, string][]): { messages: ConvMsg[] } => ({
  messages: pairs.map(([role, content], seq) => ({ role, content, seq, reasoning: "" })),
});
export async function settle(work: () => void = () => {}) {
  await act(async () => { work(); for (let i = 0; i < 12; i++) await Promise.resolve(); });
}
export class Wire {
  body: { conversation_id: string; message: string };
  controller!: ReadableStreamDefaultController<Uint8Array>;
  response: Response;
  ended = false;
  constructor(options: RequestInit) {
    this.body = JSON.parse(options.body as string);
    this.response = new Response(new ReadableStream<Uint8Array>({ start: c => { this.controller = c; } }));
  }
  async raw(text: string) { await settle(() => this.controller.enqueue(new TextEncoder().encode(text))); }
  event(value: ChatEvent) { return this.raw(`data: ${JSON.stringify(value)}\n\n`); }
  async end() { await this.raw("data: [DONE]\n\n"); await this.close(); }
  async close() { await settle(() => { this.ended = true; this.controller.close(); }); }
  async fail() { await settle(() => { this.ended = true; this.controller.error(new TypeError("Synthetic connection lost")); }); }
}
export function network() {
  const wires: Wire[] = [];
  const histories = new Map<string, ReturnType<typeof deferred<Response>>[]>();
  const lists: ReturnType<typeof deferred<Response>>[] = [];
  const cancellations: ReturnType<typeof deferred<Response>>[] = [];
  const deletions: { id: string; response: ReturnType<typeof deferred<Response>> }[] = [];
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === "/api/conversations") {
      const response = deferred<Response>(); lists.push(response); return response.promise;
    }
    const match = url.match(/^\/api\/conversations\/([^/]+)\/messages$/);
    if (match) {
      const response = deferred<Response>(); histories.set(match[1], [...(histories.get(match[1]) || []), response]); return response.promise;
    }
    if (url === "/api/chat") { const wire = new Wire(options!); wires.push(wire); return wire.response; }
    if (url === "/api/cancel") { const response = deferred<Response>(); cancellations.push(response); return response.promise; }
    if (options?.method === "DELETE") {
      const response = deferred<Response>(); deletions.push({ id: url.split("/").pop()!, response }); return response.promise;
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetch);
  return { wires, histories, lists, cancellations, deletions, fetch,
    load: async (id: string, messages = history(), index = 0) => settle(() => histories.get(id)![index].resolve(json(messages))),
    list: async (index = 0, value = conversations) => settle(() => lists[index].resolve(json(value))),
  };
}
