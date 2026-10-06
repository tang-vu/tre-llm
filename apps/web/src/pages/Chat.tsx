import React, { useEffect, useRef, useSyncExternalStore } from "react";
import { ChatSession, Message, chatSession } from "../chatSession";
import { Markdown } from "../markdown";

const EXAMPLES = [
  "Viết đoạn lịch sử về ngôi đền gần nhà tôi",
  "Hướng dẫn mình cách gỡ lỗi tốt",
  "Hà Nội có bao nhiêu quận nội thành?",
  "Tóm tắt đoạn văn này thành 3 gạch đầu dòng",
];

export default function ChatPage({ session = chatSession }: { session?: ChatSession }) {
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const conversation = state.retained.find(c => c.key === state.selected)!;
  const activeConversation = state.retained.find(c => c.key === state.active?.conversation);
  const { messages, input, error, meta, history } = conversation;
  const scrollRef = useRef<HTMLDivElement>(null);
  const composing = useRef(false);
  const canSend = session.canSend();
  const hasLocalMessages = messages.some(m => !m.saved) || !!conversation.copies.length;
  const visible = state.conversations.slice(0, 5);
  const local = state.retained.filter(c =>
    !visible.some(item => item.id === c.id) && (c.input || c.messages.length || c.copies.length || c.key === state.active?.conversation));

  useEffect(() => { void session.refreshConversations(); }, [session]);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !composing.current && !e.nativeEvent.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      void session.send();
    }
  };
  const remove = (id: string, title: string) => {
    if (window.confirm(`Xoá "${title}" và toàn bộ tin nhắn?`)) void session.deleteConversation(id);
  };

  const renderMessage = (m: Message) => (
    <div key={m.id} className={`msg ${m.role === "user" ? "user" : "bot"}`}>
      {m.reasoning && <details className="exp"><summary>suy luận</summary><div className="thinking">{m.reasoning}</div></details>}
      {m.content ? <Markdown text={m.content} /> : m.id === state.active?.assistant ? <span className="muted">…</span> : null}
      {!m.saved && m.id !== state.active?.assistant && m.id !== state.active?.user &&
        <small className="muted">Chưa xác nhận lưu; chỉ giữ trong phiên này.</small>}
    </div>
  );
  return (
    <div>
      <h1>Trò chuyện</h1>
      <p className="sub">Chạy hoàn toàn trên máy này. Không tài khoản, không telemetry.</p>
      <div className="row" style={{ marginBottom: 12 }} aria-label="Cuộc trò chuyện">
        <button className="primary" onClick={() => session.newConversation()}>+ Cuộc trò chuyện mới</button>
        {visible.map(c => (
          <span key={c.id} className="chip">
            <button className="ghost" aria-pressed={conversation.id === c.id}
              disabled={state.deleting.includes(c.id) || !!activeConversation && !activeConversation.id} onClick={() => session.select(c.id)}>
              {c.title || c.id.slice(0, 8)}
            </button>
            <button className="ghost" style={{ padding: "0 4px", fontSize: 11 }}
              disabled={state.deleting.includes(c.id) || !!activeConversation && (!activeConversation.id || activeConversation.id === c.id)}
              onClick={() => remove(c.id, c.title || c.id)} aria-label={`Xoá ${c.title || c.id}`}>×</button>
          </span>
        ))}
        {local.map(c => (
          <button key={c.key} className="ghost" aria-pressed={conversation.key === c.key}
            onClick={() => session.selectLocal(c.key)}>{!c.id && !c.messages.length ? c.input.trim().slice(0, 40) || c.title : c.title} (phiên này)</button>
        ))}
        <button className="ghost" onClick={() => void session.refreshConversations()}>Tải lại danh sách</button>
      </div>
      {state.listError && <div className="banner err" role="alert">{state.listError}</div>}
      {state.notice && <div className="banner err" role="alert">{state.notice}</div>}
      {conversation.id && <div className="row" style={{ marginBottom: 8 }}>
        <span className="muted">{conversation.title}</span>
        <button className="ghost" disabled={history === "loading" || state.active?.conversation === conversation.key || state.deleting.includes(conversation.id)}
          onClick={() => void session.loadHistory()}>Tải lại lịch sử</button>
      </div>}
      {history === "loading" && <p role="status">Đang tải lịch sử… Chờ tải xong để gửi đúng ngữ cảnh.</p>}
      {history === "error" && <p className="muted">{conversation.id ? "Tải lại lịch sử để xác nhận ngữ cảnh trước khi gửi tiếp." : "Chưa nhận được mã cuộc trò chuyện. Tạo cuộc trò chuyện mới để gửi tiếp."} Bản nháp của bạn vẫn được giữ.</p>}
      <div className="card" style={{ minHeight: 320, maxHeight: 480, overflow: "auto" }} ref={scrollRef} aria-busy={history === "loading"}>
        <div className="chat-scroll">
          {messages.length === 0 && history === "ready" && !state.active && (
            <div><p className="muted">Bắt đầu bằng một ví dụ:</p><div className="examples">
              {EXAMPLES.map(x => <button key={x} disabled={!canSend} onClick={() => void session.send(x)}>{x}</button>)}
            </div></div>
          )}
          {messages.map(renderMessage)}
          {!!conversation.copies.length && <section aria-label="Bản giữ trong phiên này">
            <h2>Nội dung chưa xác nhận lưu</h2>
            <p className="muted">Bản giữ trước khi tải lại lịch sử, có thể trùng tin nhắn đã lưu ở trên. Không tự gửi lại hoặc dùng làm ngữ cảnh.</p>
            {conversation.copies.map(renderMessage)}
          </section>}
        </div>
      </div>
      {conversation.notice && <div className="banner err" role="alert">{conversation.notice}</div>}
      {error && <div className="banner err" role="alert">{error}</div>}
      {meta && <div className="muted" role="status" style={{ fontSize: 12, marginTop: 6 }}>{meta}</div>}
      {state.active && <p className="muted" role="status">
        {!activeConversation?.id && <>Đang mở cuộc trò chuyện; chờ xác nhận trước khi chọn hoặc xoá cuộc đã lưu. </>}
        {state.active.stopping ? "Đã yêu cầu dừng; đang chờ máy chủ và luồng phản hồi kết thúc." : "Đang chờ phản hồi kết thúc."}
        {activeConversation?.key !== conversation.key && <>{" "}<button className="ghost"
          onClick={() => session.selectLocal(activeConversation!.key)}>Về cuộc trò chuyện đang chạy</button></>}
      </p>}
      {hasLocalMessages && !state.active && <p className="muted">Nội dung chưa xác nhận lưu không được tự gửi lại. Hãy sao chép nội dung cần giữ trước khi đóng hoặc tải lại trang.</p>}
      {(hasLocalMessages || input) && <button className="ghost"
        disabled={state.active?.conversation === conversation.key || history === "loading" || state.deleting.includes(conversation.id)}
        onClick={() => { if (window.confirm("Bỏ bản nháp và nội dung chưa xác nhận trong phiên này? Hãy sao chép nội dung cần giữ. Tin nhắn đã lưu trên máy chủ không bị xoá.")) session.discardDraft(); }}>Bỏ bản nháp trong phiên</button>}
      <div className="composer">
        <textarea value={input} placeholder="Nhắn tin tiếng Việt… (Enter gửi, Shift+Enter xuống dòng)"
          onChange={e => session.setInput(e.target.value)} onKeyDown={onKeyDown}
          onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} aria-label="Tin nhắn" />
        {state.active ? <button onClick={() => void session.stop()} disabled={state.active.stopping || state.active.streamSettled || state.active.terminal} title="Gửi lệnh dừng tới máy chủ; lệnh này có thể ảnh hưởng yêu cầu ở tab khác." aria-label="Dừng">Dừng</button> :
          <button className="primary" onClick={() => void session.send()} disabled={!canSend || !input.trim()} aria-label="Gửi">Gửi</button>}
      </div>
    </div>
  );
}
