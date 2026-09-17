"""tre — TreLLM command line interface."""

from __future__ import annotations

import typer

from tre_llm.cli.util import console
from tre_llm.version import __version__

app = typer.Typer(
    name="tre",
    help="TreLLM — LLM tiếng Việt, vừa sức máy bạn.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

from tre_llm.cli import documents, lab, models, train  # noqa: E402

app.add_typer(models.app, name="models", help="Quản lý model: list/pull/import/remove")
app.add_typer(documents.app, name="documents", help="Tài liệu cục bộ: add/list/remove")
app.add_typer(train.app, name="train", help="Tre Adapt: preflight/run/eval export")


def _version(value: bool) -> None:
    if value:
        console.print(f"tre {__version__}")
        raise typer.Exit()


@app.callback()
def callback(
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="In phiên bản."),
) -> None:
    pass


@app.command(help="Kiểm tra phần cứng, runtime và độ sẵn sàng (read-only).")
def doctor(json: bool = typer.Option(False, "--json", help="Xuất JSON máy đọc được.")) -> None:
    from tre_llm.cli.doctor import run

    run(json_mode=json)


@app.command(help="Lập kế hoạch triển khai theo mục tiêu (không cần tải model).")
def plan(
    goal: str = typer.Option("balanced", "--goal", help="light | balanced | quality"),
    json: bool = typer.Option(False, "--json"),
) -> None:
    from tre_llm.cli.plan_cmd import run

    run(goal=goal, json_mode=json)


@app.command(help="Thiết lập runtime + model theo kế hoạch đã chọn.")
def setup(
    goal: str = typer.Option("balanced", "--goal"),
    model: str = typer.Option("", "--model", help="registry id cụ thể"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Không hỏi xác nhận."),
    json: bool = typer.Option(False, "--json"),
) -> None:
    from tre_llm.cli.setup_cmd import run

    run(goal=goal, model_id=model, yes=yes, json_mode=json)


@app.command(help="Chat tiếng Việt streaming với model đã chọn.")
def chat(
    model: str = typer.Option("", "--model", help="registry id; mặc định theo plan/cài đặt"),
    server: str = typer.Option("", "--server", help="Base URL server ngoài (attach mode)"),
    thinking: bool = typer.Option(False, "--thinking", help="Bật reasoning của model."),
    system: str = typer.Option("Bạn là trợ lý AI trả lời bằng tiếng Việt chuẩn mực, súc tích.", "--system"),
    ctx: int = typer.Option(0, "--ctx", help="Ghi đè context size."),
    max_tokens: int = typer.Option(512, "--max-tokens"),
    once: str = typer.Option("", "--once", help="Gửi một câu hỏi rồi thoát (non-interactive)."),
) -> None:
    from tre_llm.cli.chat import run

    run(model=model, server=server, thinking=thinking, system=system, ctx=ctx, max_tokens=max_tokens, once=once)


@app.command(help="Khởi động server cục bộ: API + web UI.")
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8471, "--port"),
    model: str = typer.Option("", "--model"),
    server: str = typer.Option("", "--attach", help="Attach server ngoài thay vì tự chạy."),
) -> None:
    from tre_llm.cli.serve_cmd import run

    run(host=host, port=port, model=model, attach=server)


@app.command(help="Đo hiệu năng thật trên máy này (bounded calibration).")
def bench(
    quick: bool = typer.Option(False, "--quick", help="1 request ngắn/model."),
    model: str = typer.Option("", "--model"),
    json: bool = typer.Option(False, "--json"),
) -> None:
    from tre_llm.cli.lab import run_bench

    run_bench(quick=quick, model=model, json_mode=json)


@app.command("eval", help="Chạy bộ đánh giá tiếng Việt Tre Viet.")
def eval_cmd(
    suite: str = typer.Option("tre-viet", "--suite"),
    split: str = typer.Option("test", "--split", help="dev | test"),
    model: str = typer.Option("", "--model"),
    limit: int = typer.Option(0, "--limit"),
    judge: str = typer.Option("", "--judge", help="registry id model chấm rubric (khác model test)"),
    out: str = typer.Option("", "--out", help="Ghi report JSON/HTML vào thư mục."),
) -> None:
    from tre_llm.cli.lab import run_eval

    run_eval(suite=suite, split=split, model=model, limit=limit, judge=judge, out=out)


@app.command(help="Hỏi đáp trên tài liệu đã nạp (RAG cục bộ).")
def ask(
    question: str = typer.Argument(..., help="Câu hỏi tiếng Việt."),
    model: str = typer.Option("", "--model"),
    k: int = typer.Option(4, "--k", help="Số đoạn trích."),
) -> None:
    from tre_llm.cli.documents import run_ask

    run_ask(question=question, model=model, k=k)


@app.command(help="Xuất báo cáo hiệu năng/đánh giá đã đo.")
def report(
    format: str = typer.Option("html", "--format", help="html | md | json"),
    out: str = typer.Option("", "--out"),
) -> None:
    from tre_llm.cli.lab import run_report

    run_report(format=format, out=out)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
