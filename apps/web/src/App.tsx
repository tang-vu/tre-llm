import React, { useEffect, useState } from "react";
import { api } from "./api";
import ChatPage from "./pages/Chat";
import DocsPage from "./pages/Documents";
import LabPage from "./pages/Lab";
import MachinePage from "./pages/Machine";
import ModelsPage from "./pages/Models";

const NAV = [
  { hash: "#/may", label: "Máy của bạn", icon: "◉" },
  { hash: "#/tro-chuyen", label: "Trò chuyện", icon: "❝" },
  { hash: "#/tai-lieu", label: "Tài liệu", icon: "▤" },
  { hash: "#/phong-thu", label: "Phòng thử", icon: "⌁" },
  { hash: "#/mo-hinh", label: "Mô hình & cài đặt", icon: "⚙" },
];

function useHash() {
  const [h, setH] = useState(window.location.hash || "#/may");
  useEffect(() => {
    const fn = () => setH(window.location.hash || "#/may");
    window.addEventListener("hashchange", fn);
    return () => window.removeEventListener("hashchange", fn);
  }, []);
  return h;
}

export default function App() {
  const hash = useHash();
  const [dark, setDark] = useState(
    () => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false,
  );
  const [status, setStatus] = useState<{ upstream_ready: boolean; active_model: string } | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, [hash]);

  let page = <MachinePage />;
  if (hash.startsWith("#/tro-chuyen")) page = <ChatPage />;
  else if (hash.startsWith("#/tai-lieu")) page = <DocsPage />;
  else if (hash.startsWith("#/phong-thu")) page = <LabPage />;
  else if (hash.startsWith("#/mo-hinh")) page = <ModelsPage />;

  return (
    <div className="app">
      <nav className="side" aria-label="Điều hướng chính">
        <div className="brand">
          TreLLM
          <small>LLM tiếng Việt, vừa sức máy bạn</small>
        </div>
        {NAV.map((n) => (
          <a key={n.hash} href={n.hash} className={hash.startsWith(n.hash) ? "active" : ""}>
            <span aria-hidden>{n.icon}</span>
            <span className="lbl">{n.label}</span>
          </a>
        ))}
        <div className="foot">
          <label style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
            <input type="checkbox" checked={dark} onChange={(e) => setDark(e.target.checked)} />
            <span className="lbl">Tối</span>
          </label>
          <div style={{ marginTop: 8 }} className="lbl">
            {status ? (
              status.upstream_ready ? (
                <span className="chip ok">{status.active_model}</span>
              ) : (
                <span className="chip warn">chưa có model</span>
              )
            ) : (
              <span className="chip">offline?</span>
            )}
          </div>
        </div>
      </nav>
      <main>
        <div className="wrap">{page}</div>
      </main>
    </div>
  );
}
