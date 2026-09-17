"""Evidence report builder — JSON + human-readable, redacted by default."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from tre_llm import paths


def _redact(text: str) -> str:
    """Strip personal paths and home dirs from report output."""
    home = str(Path.home())
    text = text.replace(home, "~")
    text = re.sub(r"/mnt/[a-z]/[^\s'\"]*", "<path>", text)
    text = re.sub(r"[A-Za-z]:\\[^\s'\"]*", "<path>", text)
    return text


def build_report(format: str = "html", out: str | None = None) -> Path:
    """Aggregate eval/bench JSON results into one report file."""
    results = sorted(paths.eval_results_dir().glob("*.json"))
    out_dir = Path(out) if out else paths.reports_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    payloads = []
    for f in results:
        try:
            payloads.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue

    if format == "json":
        dest = out_dir / f"tre-report-{stamp}.json"
        dest.write_text(_redact(json.dumps(payloads, ensure_ascii=False, indent=2)), encoding="utf-8")
        return dest

    if format == "md":
        dest = out_dir / f"tre-report-{stamp}.md"
        dest.write_text(_redact(_to_markdown(payloads)), encoding="utf-8")
        return dest

    dest = out_dir / f"tre-report-{stamp}.html"
    dest.write_text(_redact(_to_html(payloads)), encoding="utf-8")
    return dest


def _to_markdown(payloads: list) -> str:
    lines = ["# TreLLM report", "", f"Generated: {datetime.now(UTC).isoformat()}", ""]
    for p in payloads:
        if "decode_tps" in p:  # bench report
            lines.append(f"## Bench — {p.get('model_id')}")
            for k in ("load_ms", "ttft_ms", "decode_tps", "prompt_tps", "peak_rss_mb"):
                v = p.get(k) or {}
                if v.get("value") is not None:
                    lines.append(f"- {k}: {v['value']} {v.get('unit', '')} [{v.get('evidence')}]")
            lines.append(f"- samples: {p.get('samples')}, failures: {p.get('failures')}")
        if "summary" in p:  # eval report
            s = p["summary"]
            lines.append(f"## Eval {p.get('suite')} ({p.get('split')}) — {p.get('model_id')}")
            lines.append(f"- graded: {s.get('graded')}, ungraded: {s.get('ungraded')}, errors: {s.get('errors')}")
            lines.append(f"- mean score: {s.get('mean_score')}, pass rate: {s.get('pass_rate')}")
        lines.append("")
    return "\n".join(lines)


def _to_html(payloads: list) -> str:
    import html as H

    rows = []
    for p in payloads:
        kind = "bench" if "decode_tps" in p else "eval"
        title = f"{kind}: {p.get('model_id', p.get('suite', ''))}"
        rows.append(f"<h2>{H.escape(title)}</h2><pre>{H.escape(json.dumps(p, ensure_ascii=False, indent=2))}</pre>")
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>TreLLM report</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1f1c}}
pre{{background:#f4f2ec;padding:1rem;border-radius:8px;overflow:auto;font-size:12px}}
h1{{color:#1e6b46}}</style></head><body>
<h1>TreLLM evidence report</h1><p>Generated {datetime.now(UTC).isoformat()} — dữ liệu đo thật trên máy chạy.</p>
{''.join(rows)}</body></html>"""
