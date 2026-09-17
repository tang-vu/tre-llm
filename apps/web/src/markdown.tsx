// Minimal safe markdown renderer — no innerHTML, everything is React nodes.
// Supports: headings, bold/italic, inline code, fenced code, lists, links,
// paragraphs. No raw HTML is ever rendered — the sanitizer is structural.

import React from "react";

function inline(text: string, keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  // token order: `code` | **bold** | *italic* | [text](url)
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(\[[^\]]*\]\([^)\s]+\))/g;
  let last = 0, i = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const k = `${keyBase}-${i++}`;
    if (tok.startsWith("`")) out.push(<code key={k} className="mono">{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("**")) out.push(<strong key={k}>{inline(tok.slice(2, -2), k)}</strong>);
    else if (tok.startsWith("*")) out.push(<em key={k}>{inline(tok.slice(1, -1), k)}</em>);
    else {
      const mm = tok.match(/\[([^\]]*)\]\(([^)\s]+)\)/)!;
      const href = mm[2];
      const safe = /^https?:\/\//.test(href) ? href : "#"; // no javascript: ever
      out.push(<a key={k} href={safe} rel="noreferrer noopener" target="_blank">{mm[1]}</a>);
    }
    last = m.index! + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0, key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++;
      blocks.push(
        <pre key={key++} className="code"><code>{buf.join("\n")}{lang ? `\n` : ""}</code></pre>,
      );
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) {
      const level = Math.min(h[1].length + 1, 6);
      const Tag = `h${level}` as keyof JSX.IntrinsicElements;
      blocks.push(<Tag key={key++}>{inline(h[2], `h${key}`)}</Tag>);
      i++;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={key++}>{items.map((it, j) => <li key={j}>{inline(it, `li${key}-${j}`)}</li>)}</ul>,
      );
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
        i++;
      }
      blocks.push(
        <ol key={key++}>{items.map((it, j) => <li key={j}>{inline(it, `ol${key}-${j}`)}</li>)}</ol>,
      );
      continue;
    }
    if (line.trim()) {
      const buf = [line];
      i++;
      while (i < lines.length && lines[i].trim() && !/^(#{1,4}|\s*[-*]|\s*\d+[.)]|```)/.test(lines[i])) {
        buf.push(lines[i++]);
      }
      blocks.push(<p key={key++}>{inline(buf.join(" "), `p${key}`)}</p>);
      continue;
    }
    i++;
  }
  return <div>{blocks}</div>;
}
