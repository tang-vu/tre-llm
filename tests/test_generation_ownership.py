"""Generation admission and protocol regressions; no model or network calls."""

import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from tests.generation_helpers import assert_reusable, events, in_flight, request
from tre_llm.runtimes.manager import RunningServer
from tre_llm.schemas import PlanChoice
from tre_llm.server.app import state
from tre_llm.storage.db import get_db


@pytest.mark.parametrize("first_kind", ["stream", "nonstream", "persisted"])
@pytest.mark.parametrize("second_kind", ["stream", "nonstream", "persisted"])
def test_generation_rejects_overlap(harness, first_kind, second_kind):
    with in_flight(harness, first_kind) as first:
        assert not first.done()
        assert state.gen_lock.locked()
        second = request(harness.client, second_kind, "second")
        if second_kind == "persisted":
            assert second.status_code == 200  # Existing persisted-chat SSE busy contract.
            assert len(events(second)) == 1
            assert events(second)[0]["type"] == "error"
            assert "bận" in events(second)[0]["error"]
        else:
            assert second.status_code == 409
        assert harness.upstream.calls == ["first"]
    assert_reusable(harness)


def test_rejected_request_does_not_clear_current_cancellation(harness):
    with in_flight(harness) as first:
        assert harness.client.post("/api/cancel").json() == {"cancelled": 1}
        assert request(harness.client, "nonstream", "second").status_code == 409
        assert harness.provider._cancel.is_set()
        assert state.gen_lock.locked()
    assert events(first.result())[-1]["choices"][0]["finish_reason"] == "cancelled"
    assert_reusable(harness)


def test_model_runtime_cannot_switch_during_stream(harness, monkeypatch):
    from tre_llm import registry
    from tre_llm.runtimes import manager

    stopped, started = [], []
    monkeypatch.setattr(harness.runtime, "process", object())
    monkeypatch.setattr(harness.runtime, "stop", lambda: stopped.append("old-runtime"))
    monkeypatch.setattr(
        registry,
        "installed",
        lambda: {
            "fake": SimpleNamespace(local_path="/synthetic/old.gguf"),
            "fake-new": SimpleNamespace(local_path="/synthetic/new.gguf"),
        },
    )

    def fake_start(model, path):
        started.append(model)
        return RunningServer(
            harness.provider, None, harness.provider.base_url, PlanChoice(artifact_id=model), []
        )

    monkeypatch.setattr(manager, "start_for_model", fake_start)
    with in_flight(harness) as first:
        switched = harness.client.post("/api/models/select", json={"model_id": "fake-new"})
        assert switched.status_code == 409
        assert stopped == [] and started == []
        assert state.server is harness.runtime and state.active_model == "fake"
        # Model selection already saves the desired setting before checking the
        # generation lock. This test promises runtime safety, not setting rollback.
        assert get_db().get_setting("active_model") == "fake-new"
    assert all(event["model"] == "fake" for event in events(first.result()))
    switched = harness.client.post("/api/models/select", json={"model_id": "fake-new"})
    assert switched.status_code == 200 and switched.json()["applied"]
    assert stopped == ["old-runtime"] and started == ["fake-new"]
    assert_reusable(harness)


def test_stream_preserves_utf8_reasoning_finish_usage_and_timings(harness):
    response = request(harness.client, "stream", "normal")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    chunks = events(response)
    assert len({chunk["id"] for chunk in chunks}) == 1
    assert all(chunk["object"] == "chat.completion.chunk" and chunk["model"] == "fake" for chunk in chunks)
    assert chunks[0]["choices"][0]["delta"] == {"reasoning_content": "Suy nghĩ"}
    assert chunks[1]["choices"][0]["delta"] == {"content": "normal Tiếng Việt"}
    assert chunks[2]["choices"][0]["delta"] == {"content": " last"}
    assert chunks[-1]["choices"] == [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    assert chunks[-1]["usage"] == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
    assert chunks[-1]["timings"] == {"predicted_per_second": 10.0}
    assert response.content.endswith(b"data: [DONE]\n\n")
    assert_reusable(harness)


@pytest.mark.parametrize("kind", ["stream", "nonstream"])
@pytest.mark.parametrize("label", ["http-error", "transport-error", "read-error"])
def test_provider_errors_release_ownership(harness, kind, label):
    response = request(harness.client, kind, label)
    if kind == "stream":
        assert response.status_code == 200
        error = events(response)[-1]
        assert error["choices"] == [{"index": 0, "delta": {}, "finish_reason": "error"}]
        assert "synthetic" in error["error"]
        assert response.content.endswith(b"data: [DONE]\n\n")
    else:
        assert response.status_code == 502
    assert_reusable(harness)


def test_unexpected_iteration_error_releases_ownership(harness):
    with pytest.raises(RuntimeError, match="synthetic unexpected failure"):
        request(harness.client, "stream", "unexpected-error")
    assert_reusable(harness)


def test_invalid_request_does_not_acquire_ownership(harness):
    response = harness.client.post("/v1/chat/completions", json={"messages": [], "stream": True})
    assert response.status_code == 422
    assert harness.upstream.calls == []
    assert_reusable(harness)


def test_response_construction_failure_does_not_acquire_ownership(harness, monkeypatch):
    from tre_llm.server import app as app_module
    from tre_llm.server.streaming import GenerationStreamingResponse

    class FailedResponse(GenerationStreamingResponse):
        def __init__(self, *args):
            raise RuntimeError("synthetic response construction failure")

    with monkeypatch.context() as patch:
        patch.setattr(app_module, "GenerationStreamingResponse", FailedResponse)
        with pytest.raises(RuntimeError, match="synthetic response construction failure"):
            request(harness.client, "stream", "unused")
    assert harness.upstream.calls == []
    assert_reusable(harness)


def test_source_setup_error_before_headers_releases_ownership(harness, monkeypatch):
    from tre_llm.server import app as app_module

    def fail_request(**kwargs):
        raise RuntimeError("synthetic request setup failure")

    with monkeypatch.context() as patch:
        patch.setattr(app_module, "GenerationRequest", fail_request)
        with pytest.raises(RuntimeError, match="synthetic request setup failure"):
            request(harness.client, "stream", "unused")
    assert harness.upstream.calls == []
    assert_reusable(harness)


def test_pending_provider_close_keeps_generation_owned(harness, monkeypatch):
    from tests.generation_helpers import GateStream

    closing, finish_close = threading.Event(), threading.Event()
    close = GateStream.close

    def delayed_close(stream):
        if stream.label == "normal":
            closing.set()
            assert finish_close.wait(5)
        close(stream)

    monkeypatch.setattr(GateStream, "close", delayed_close)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(request, harness.client, "stream", "normal")
        try:
            assert closing.wait(5)
            assert state.gen_lock.locked() and state.current_cancel
            assert request(harness.client, "stream", "second").status_code == 409
            assert not first.done() and harness.upstream.calls == ["normal"]
        finally:
            finish_close.set()
            assert first.result(timeout=5).status_code == 200
    assert_reusable(harness)
