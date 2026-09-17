import React, { useEffect, useRef, useState } from "react";
import { api, ConvEntry, streamChat } from "../api";
import { Markdown } from "../markdown";

interface Msg { role: string; content: string; reasoning?: string }

const EXAMPLES = [
  "Viết đoạn lịch sử về ngôi đền gần nhà tôi",
  "Hướng dẫn mình cách gỡ lỗi tốt",
  "Hà Nội có bao nhiêu quận nội thành?",
  "Tóm tắt đoạn văn này thành 3 gạch đầu dòng",
];

export default function ChatPage() {
  const [convs, setConvs] = useState<ConvEntry[]>([]);
  const [convId, setConvId] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [meta, setMeta] = useState("");
  const [err, setErr] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const composing = useRef(false); // Vietnamese IME guard

  const refreshConvs = () => api.conversations().then(setConvs).catch(() => {});

  useEffect(() => { refreshConvs(); }, []);

  useEffect(() => {
    if (!convId) { setMsgs([]); return; }
    api.convMessages(convId).then((r) => setMsgs(r.messages)).catch(() => {});
  }, [convId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [msgs]);

  const send = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || busy) return;
    setInput("");
    setErr("");
    setMeta("");
    setBusy(true);
    const ac = new AbortController();
    abortRef.current = ac;
    setMsgs((m) => [...m, { role: "user", content: msg }, { role: "assistant", content: "" }]);
    let acc = "", reasoning = "";
    try {
      for await (const ev of streamChat(
        { conversation_id: convId, message: msg, enable_thinking: false },
        ac.signal,
      )) {
        if (ev.type === "conv") setConvId(ev.id);
        else if (ev.type === "token") {
          acc += ev.text;
          setMsgs((m) => {
            const c = [...m];
            c[c.length - 1] = { role: "assistant", content: acc, reasoning };
            return c;
          });
        } else if (ev.type === "reasoning") {
          reasoning += ev.text;
        } else if (ev.type === "done") {
          const t = ev.timings?.predicted_per_second;
          setMeta(
            `xong (${ev.finish_reason})` + (t ? ` — ${t.toFixed(1)} tok/s` : ""),
          );
        } else if (ev.type === "error") {
          setErr(ev.error);
          setMsgs((m) => m.slice(0, -1));
        }
      }
      refreshConvs();
    } catch (e) {
      if (!ac.signal.aborted) setErr(String(e));
      setMsgs((m) => m.slice(0, -1));
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  const stop = async () => {
    abortRef.current?.abort();
    await api.cancel().catch(() => {});
    setBusy(false);
    setMeta("đã dừng");
  };

  const newConv = () => { setConvId(""); setMsgs([]); setMeta(""); setErr(""); };
  const delConv = async (id: string) => {
    await api.deleteConversation(id).catch(() => {});
    if (id === convId) newConv();
    refreshConvs();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Don't send Enter while Vietnamese IME composition is in progress
    if (e.key === "Enter" && !e.shiftKey && !composing.current && !(e.nativeEvent as any).isComposing) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <div>
      <h1>Trò chuyện</h1>
      <p className="sub">Chạy hoàn toàn trên máy này. Không tài khoản, không telemetry.</p>

      <div className="row" style={{ marginBottom: 12 }}>
        <button className="primary" onClick={newConv}>+ Cuộc trò chuyện mới</button>
        {convs.slice(0, 5).map((c) => (
          <span key={c.id} className="chip" style={{ cursor: "pointer" }}
            onClick={() => setConvId(c.id)}>
            {c.title || c.id.slice(0, 8)}{" "}
            <button className="ghost" style={{ padding: "0 4px", fontSize: 11 }}
              onClick={(e) => { e.stopPropagation(); void delConv(c.id); }}
              aria-label="Xoá cuộc trò chuyện">×</button>
          </span>
        ))}
      </div>

      <div className="card" style={{ minHeight: 320, maxHeight: 480, overflow: "auto" }} ref={scrollRef}>
        <div className="chat-scroll">
          {msgs.length === 0 && !busy && (
            <div>
              <p className="muted">Bắt đầu bằng một ví dụ:</p>
              <div className="examples">
                {EXAMPLES.map((x) => (
                  <button key={x} onClick={() => void send(x)}>{x}</button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={`msg ${m.role === "user" ? "user" : "bot"}`}>
              {m.reasoning && (
                <details className="exp">
                  <summary>suy luận</summary>
                  <div className="thinking">{m.reasoning}</div>
                </details>
              )}
              {m.content ? <Markdown text={m.content} /> : m.role === "assistant" && busy ? <span className="muted">…</span> : null}
            </div>
          ))}
        </div>
      </div>

      {err && <div className="banner err">{err}</div>}
      {meta && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{meta}</div>}

      <div className="composer">
        <textarea
          value={input}
          placeholder="Nhắn tin tiếng Việt… (Enter gửi, Shift+Enter xuống dòng)"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          onCompositionStart={() => { composing.current = true; }}
          onCompositionEnd={() => { composing.current = false; }}
          aria-label="Tin nhắn"
        />
        {busy ? (
          <button onClick={stop} aria-label="Dừng">Dừng</button>
        ) : (
          <button className="primary" onClick={() => void send()} disabled={!input.trim()} aria-label="Gửi">Gửi</button>
        )}
      </div>
    </div>
  );
}
