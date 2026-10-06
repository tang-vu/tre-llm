import { api, ChatEvent, ConvEntry, streamChat } from "./api";

export interface Message {
  id: number;
  role: string;
  content: string;
  reasoning?: string;
  saved: boolean;
}
export interface Conversation {
  key: number;
  id: string;
  title: string;
  input: string;
  messages: Message[];
  copies: Message[];
  history: "ready" | "loading" | "error";
  error: string;
  meta: string;
  notice: string;
}
interface Request {
  conversation: number;
  user: number;
  assistant: number;
  stopping: boolean;
  terminal: boolean;
  streamSettled: boolean;
  cancelSettled: boolean;
}
interface Snapshot {
  conversations: ConvEntry[];
  retained: Conversation[];
  selected: number;
  active: Request | null;
  deleting: string[];
  listError: string;
  notice: string;
}
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
const hasLocalText = (c: Conversation) => !!c.input || !!c.copies.length || c.messages.some(m => !m.saved);
const MAX_RETAINED = 20;

// One owner per browser page, including while the chat route is unmounted. No
// localStorage: drafts and unconfirmed output live only until this page closes.
export class ChatSession {
  private nextId = 0;
  private listVersion = 0;
  private historyVersions = new Map<number, number>();
  private listeners = new Set<() => void>();
  private snapshot: Snapshot;

  constructor() {
    const conversation = this.blank();
    this.snapshot = { conversations: [], retained: [conversation], selected: conversation.key,
      active: null, deleting: [], listError: "", notice: "" };
  }
  private blank(): Conversation {
    return { key: ++this.nextId, id: "", title: "Cuộc trò chuyện mới", input: "", messages: [], copies: [], history: "ready", error: "", meta: "", notice: "" };
  }
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private emit(update: Partial<Snapshot> = {}) {
    this.snapshot = { ...this.snapshot, ...update };
    this.listeners.forEach(listener => listener());
  }
  private conversation(key = this.snapshot.selected) {
    return this.snapshot.retained.find(c => c.key === key)!;
  }
  private update(key: number, update: Partial<Conversation>) {
    this.emit({ retained: this.snapshot.retained.map(c => c.key === key ? { ...c, ...update } : c) });
  }
  setInput(input: string) { this.update(this.snapshot.selected, { input }); }
  hasUnsavedWork = () => !!this.snapshot.active || this.snapshot.retained.some(hasLocalText);

  async refreshConversations() {
    const version = ++this.listVersion;
    try {
      const conversations = await api.conversations();
      // A new ID can enter the list before its conv event arrives. Publishing it
      // now would let selection create a second view for the still-unbound owner.
      const active = this.snapshot.active;
      if (version === this.listVersion && (!active || this.conversation(active.conversation).id)) {
        this.emit({ conversations, listError: "" });
      }
    } catch (error) {
      if (version === this.listVersion) this.emit({ listError: `Không tải được danh sách: ${errorText(error)}` });
    }
  }
  private retain(conversation: Conversation) {
    const retained = [...this.snapshot.retained];
    if (retained.length >= MAX_RETAINED) {
      const index = retained.findIndex(c => c.key !== this.snapshot.active?.conversation && !hasLocalText(c));
      if (index < 0) {
        this.emit({ notice: "Đã giữ 20 cuộc trò chuyện có bản nháp. Sao chép rồi bỏ bản nháp không cần giữ để mở cuộc trò chuyện khác." });
        return false;
      }
      this.historyVersions.delete(retained[index].key);
      retained.splice(index, 1);
    }
    this.emit({ retained: [...retained, conversation], selected: conversation.key, notice: "" });
    return true;
  }
  newConversation() {
    const current = this.conversation();
    if (!current.id && !current.input && !current.messages.length) return;
    this.retain(this.blank());
  }
  selectLocal(key: number) {
    if (this.snapshot.retained.some(c => c.key === key)) this.emit({ selected: key, notice: "" });
  }
  select(id: string) {
    const active = this.snapshot.active;
    if (this.snapshot.deleting.includes(id) || active && !this.conversation(active.conversation).id) return;
    const retained = this.snapshot.retained.find(c => c.id === id);
    if (retained) { this.selectLocal(retained.key); return; }
    const conversation = { ...this.blank(), id, title: this.snapshot.conversations.find(c => c.id === id)?.title || id };
    if (this.retain(conversation)) void this.loadHistory(conversation.key);
  }
  async loadHistory(key = this.snapshot.selected) {
    const conversation = this.conversation(key);
    if (!conversation?.id || this.snapshot.active?.conversation === key || this.snapshot.deleting.includes(conversation.id)) return;
    const version = (this.historyVersions.get(key) || 0) + 1;
    this.historyVersions.set(key, version);
    this.update(key, { history: "loading", error: "" });
    try {
      const { messages } = await api.convMessages(conversation.id);
      if (this.historyVersions.get(key) !== version) return;
      const current = this.conversation(key);
      this.update(key, { history: "ready", messages: messages.map(m => ({ ...m, id: ++this.nextId, saved: true })),
        copies: [...current.copies, ...current.messages.filter(m => !m.saved)], error: "", meta: "" });
    } catch (error) {
      if (this.historyVersions.get(key) === version) this.update(key, { history: "error", error: `Không tải được lịch sử: ${errorText(error)}` });
    }
  }
  discardDraft() {
    const c = this.conversation();
    if (this.snapshot.active?.conversation === c.key || c.history === "loading" || this.snapshot.deleting.includes(c.id)) return;
    if (c.id) this.update(c.key, { input: "", copies: [], messages: c.messages.filter(m => m.saved), error: "", meta: "", notice: "" });
    else {
      const blank = this.blank();
      this.emit({ retained: this.snapshot.retained.map(item => item.key === c.key ? blank : item), selected: blank.key, notice: "" });
    }
  }
  async deleteConversation(id: string) {
    // /api/cancel is global and an active stream still needs its persistence target.
    const active = this.snapshot.active;
    if (this.snapshot.deleting.includes(id) || active && (!this.conversation(active.conversation).id || this.conversation(active.conversation).id === id)) return;
    this.emit({ deleting: [...this.snapshot.deleting, id], notice: "" });
    try {
      await api.deleteConversation(id);
      ++this.listVersion; // A pre-delete list response must not resurrect the item.
      const removed = this.snapshot.retained.find(c => c.id === id);
      const draft = removed?.input ? { ...this.blank(), input: removed.input } : null;
      const retained = this.snapshot.retained.filter(c => c.id !== id);
      if (draft) retained.push(draft);
      let selected = this.snapshot.selected;
      if (!retained.some(c => c.key === selected)) {
        const next = draft || this.blank();
        if (!draft) retained.push(next);
        selected = next.key;
      }
      for (const c of this.snapshot.retained.filter(c => c.id === id)) this.historyVersions.delete(c.key);
      this.emit({ retained, selected, conversations: this.snapshot.conversations.filter(c => c.id !== id) });
      void this.refreshConversations();
    } catch (error) {
      // A lost DELETE response can hide a committed deletion. Never send into
      // cached history until a later read establishes this ID's actual context.
      for (const c of this.snapshot.retained.filter(c => c.id === id)) {
        this.historyVersions.set(c.key, (this.historyVersions.get(c.key) || 0) + 1);
        this.update(c.key, { history: "error", error: "Chưa xác nhận kết quả xoá. Tải lại lịch sử trước khi gửi tiếp." });
      }
      this.emit({ notice: `Chưa xác nhận xoá cuộc trò chuyện: ${errorText(error)}. Hãy kiểm tra danh sách trước khi thử lại.` });
    } finally {
      this.emit({ deleting: this.snapshot.deleting.filter(item => item !== id) });
    }
  }
  canSend() {
    const c = this.conversation();
    return !this.snapshot.active && c.history === "ready" && !this.snapshot.deleting.includes(c.id);
  }
  private message(request: Request, id: number, update: Partial<Message>) {
    const c = this.conversation(request.conversation);
    this.update(c.key, { messages: c.messages.map(m => m.id === id ? { ...m, ...update } : m) });
  }
  async send(text?: string) {
    const content = (text ?? this.conversation().input).trim();
    if (!content || !this.canSend()) return;
    const c = this.conversation();
    const request: Request = { conversation: c.key, user: ++this.nextId, assistant: ++this.nextId,
      stopping: false, terminal: false, streamSettled: false, cancelSettled: true };
    // Set ownership synchronously: repeated clicks/Enter cannot issue two POSTs.
    this.emit({ active: request });
    this.update(c.key, { input: text === undefined ? "" : c.input, error: "", meta: "", notice: "", title: c.title === "Cuộc trò chuyện mới" ? content.slice(0, 40) : c.title,
      messages: [...c.messages, { id: request.user, role: "user", content, saved: false },
        { id: request.assistant, role: "assistant", content: "", saved: false }] });
    let answer = "", reasoning = "", done = false, failed = false;
    try {
      for await (const ev of streamChat({ conversation_id: c.id, message: content, enable_thinking: false })) {
        if (this.snapshot.active !== request) break;
        if (ev.type === "conv" && !failed && !done) {
          // The server has saved the user row; do not fetch user-only history.
          const assigned = !this.conversation(c.key).id;
          this.update(c.key, { id: ev.id });
          this.message(request, request.user, { saved: true });
          if (assigned) void this.refreshConversations();
        } else if (ev.type === "token" && !done && !failed) {
          answer += ev.text;
          this.message(request, request.assistant, { content: answer });
        } else if (ev.type === "reasoning" && !done && !failed) {
          reasoning += ev.text;
          this.message(request, request.assistant, { reasoning });
        } else if (ev.type === "error") {
          failed = true;
          request.terminal = true;
          this.update(c.key, { history: "error", error: ev.error, meta: "Phản hồi bị gián đoạn. Nội dung chưa xác nhận lưu được giữ trong phiên này." });
        } else if (ev.type === "done" && !failed && !done) {
          done = true;
          request.terminal = true;
          this.message(request, request.assistant, { saved: true });
          this.update(c.key, { meta: completion(ev, !!answer) });
        }
      }
      if (!done && !failed) this.update(c.key, { history: "error", error: "Luồng kết thúc mà chưa xác nhận hoàn tất.", meta: "Nội dung chưa xác nhận lưu được giữ trong phiên này; không tự gửi lại." });
    } catch (error) {
      this.update(c.key, { history: done ? "ready" : "error", error: `Mất kết nối: ${errorText(error)}`, meta: done ? this.conversation(c.key).meta : "Chưa xác nhận lưu. Nội dung được giữ trong phiên này; không tự gửi lại." });
    } finally {
      request.streamSettled = true;
      this.release(request);
      void this.refreshConversations();
    }
  }
  private release(request: Request) {
    if (this.snapshot.active === request && request.streamSettled && request.cancelSettled) this.emit({ active: null });
    else this.emit();
  }
  async stop() {
    const request = this.snapshot.active;
    if (!request || request.stopping || request.streamSettled || request.terminal) return;
    request.stopping = true;
    request.cancelSettled = false;
    this.emit();
    // Do not abort the reader: cancel only acknowledges the signal, not completion.
    // Drain this stream through EOF before another chat can use the global server.
    try { await api.cancel(); }
    catch (error) {
      this.update(request.conversation, { notice: `Chưa xác nhận lệnh dừng: ${errorText(error)}.` });
    } finally {
      request.cancelSettled = true;
      this.release(request);
    }
  }
}
function completion(ev: Extract<ChatEvent, { type: "done" }>, hasAnswer: boolean) {
  const speed = ev.timings?.predicted_per_second;
  const label = ev.finish_reason === "cancelled" ? "Đã dừng; phần phản hồi đã nhận được lưu." :
    ev.finish_reason === "length" ? "Đã đạt giới hạn độ dài; phản hồi đã được lưu." : "Đã hoàn tất và lưu phản hồi.";
  return label + (!hasAnswer ? " Chưa nhận được nội dung trả lời." : "") + (typeof speed === "number" && Number.isFinite(speed) && speed > 0 ? ` (${speed.toFixed(1)} tok/s)` : "");
}
export const chatSession = new ChatSession();
