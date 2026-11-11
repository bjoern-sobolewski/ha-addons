"""Verify Responses controls and continuation against an isolated synthetic upstream."""

import base64
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile


CONTEXT_MANAGEMENT = [{"type": "compaction", "compact_threshold": 16384}]
USAGE = {
    "input_tokens": 2048,
    "input_tokens_details": {
        "cached_tokens": 1024,
        "cache_write_tokens": 512,
        "cache_write_tokens_details": {"ttl_30m_tokens": 256, "ttl_12h_tokens": 256},
    },
    "output_tokens": 16,
    "output_tokens_details": {"reasoning_tokens": 8},
    "total_tokens": 2064,
}
ENCRYPTED_REASONING = base64.urlsafe_b64encode(bytes([128]) + bytes(72)).decode().rstrip("=")


def mock():
    from aiohttp import web

    counts = {"http": 0, "websocket": 0, "fallback_handshake": 0}

    def response(body, transport):
        counts[transport] += 1
        assert body["max_output_tokens"] == 64
        assert "max_completion_tokens" not in body
        assert body["context_management"] == CONTEXT_MANAGEMENT
        assert body["prompt_cache_key"] == "synthetic-cache"
        assert "prompt_cache_options" not in body and "prompt_cache_retention" not in body
        assert "prompt_cache_breakpoint" not in json.dumps(body["input"])
        assert body["tool_choice"]["type"] == "allowed_tools"
        assert next(tool for tool in body["tools"] if tool.get("name") == "lookup")["defer_loading"]
        items = body["input"]
        previous = body.get("previous_response_id")
        if previous:
            assert items == [{"type": "function_call_output", "call_id": "call_synthetic", "output": "7"}]
            output = [{"type": "compaction", "id": "cmp_synthetic", "encrypted_content": "opaque-compaction"}]
        elif any(item.get("type") == "compaction" for item in items):
            assert len(items) == 2 and items[0]["encrypted_content"] == "opaque-compaction"
            output = []
        elif any(item.get("type") == "reasoning" for item in items):
            assert next(item for item in items if item.get("type") == "reasoning")["encrypted_content"] == ENCRYPTED_REASONING
            assert [item["phase"] for item in items if item.get("role") == "assistant"] == ["commentary", "partial_answer", "final_answer"]
            assert [item["call_id"] for item in items if item.get("type") in ("function_call", "function_call_output")] == ["call_synthetic", "call_synthetic"]
            output = []
        else:
            # Custom aliases lack native model capability metadata, so the
            # existing thinking pipeline collapses updates to the latest effort.
            assert not any(item.get("type") == "configuration_update" for item in items)
            assert body["reasoning"]["effort"] == "low"
            output = [
                {"type": "reasoning", "id": "rs_synthetic", "summary": [], "encrypted_content": ENCRYPTED_REASONING},
                *[{"type": "message", "role": "assistant", "id": "msg_" + phase,
                   "phase": phase, "content": [{"type": "output_text", "text": "synthetic"}]}
                  for phase in ("commentary", "partial_answer", "final_answer")],
                {"type": "function_call", "id": "fc_synthetic", "call_id": "call_synthetic", "name": "lookup", "arguments": "{}"},
            ]
        return {"type": "response.completed", "response": {
            "id": f"resp_{transport}_{counts[transport]}", "model": "gpt-6.1-sol",
            "status": "completed", "output": output, "usage": USAGE,
        }}

    async def responses(request):
        assert request.headers.get("Authorization") == "Bearer fake-compat-account"
        ws = web.WebSocketResponse(compress=False)
        if ws.can_prepare(request).ok:
            if request.path.startswith("/fallback/"):
                counts["fallback_handshake"] += 1
                return web.Response(status=426)
            await ws.prepare(request)
            async for message in ws:
                if message.type == web.WSMsgType.TEXT:
                    await ws.send_json(response(json.loads(message.data), "websocket"))
            return ws
        event = response(await request.json(), "http")
        return web.Response(text="data: " + json.dumps(event) + "\n\n", content_type="text/event-stream")

    async def stats(_request):
        return web.json_response(counts)

    app = web.Application()
    app.router.add_route("*", "/responses", responses)
    app.router.add_route("*", "/fallback/responses", responses)
    app.router.add_get("/stats", stats)
    web.run_app(app, port=9000, print=None)


def main():
    import yaml
    from websockets.exceptions import ConnectionClosed
    from websockets.sync.client import connect
    from smoke import docker, eventually, request

    root = Path(__file__).resolve().parents[1]
    prefix = "codex-compat-" + secrets.token_hex(4)
    network, volume = prefix + "-net", prefix + "-data"
    cpa, upstream = prefix + "-cpa", prefix + "-mock"
    key, management = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        config = temp / "config"
        config.mkdir()
        providers = {"api-keys": {"codex": [
            {"name": alias, "base-url": "http://mock:9000" + suffix,
             "keys": [{"api-key": "fake-compat-account", "websockets": True}],
             "models": [{"name": "gpt-6.1-sol", "alias": alias}]}
            for alias, suffix in (("compat-test", ""), ("compat-fallback", "/fallback"))
        ]}}
        (config / "providers.yaml").write_text(yaml.safe_dump(providers))
        (temp / "options.json").write_text(json.dumps({"api_keys": [key], "management_key": management}))
        try:
            docker("network", "create", network)
            docker("volume", "create", volume)
            docker("run", "-d", "--name", upstream, "--network", network, "--network-alias", "mock",
                   "-v", f"{root / 'tests'}:/test:ro", "python:3.13-alpine", "sh", "-c",
                   "pip install -q aiohttp==3.13.3 && python /test/codex_compatibility_flow.py --mock")

            def stats():
                return json.loads(docker("exec", upstream, "python", "-c",
                    'import urllib.request;print(urllib.request.urlopen("http://localhost:9000/stats").read().decode())'))

            eventually(lambda: stats() == {"http": 0, "websocket": 0, "fallback_handshake": 0}, timeout=90)
            docker("create", "--init", "--name", cpa, "--network", network, "-v", volume + ":/data",
                   "-v", f"{config}:/config:ro", "-p", "127.0.0.1::8080", os.environ.get("CPA_TEST_IMAGE", "ha-cpa-test:local"))
            docker("cp", str(temp / "options.json"), cpa + ":/data/options.json")
            docker("start", cpa)
            api = "http://" + docker("port", cpa, "8080/tcp").splitlines()[0]
            headers = {"Authorization": "Bearer " + key}
            eventually(lambda: request(api + "/v1/models", headers)[0] == 200)

            def fields(model="compat-test", lite=False):
                return {"model": model, "instructions": "Synthetic compatibility check.",
                        "input": [{"type": "configuration_update", "reasoning": {"effort": "low"}},
                                  {"role": "user", "content": [{"type": "input_text", "text": "synthetic", "prompt_cache_breakpoint": {"mode": "explicit"}}]}],
                        "max_completion_tokens": 64, "context_management": CONTEXT_MANAGEMENT,
                        "prompt_cache_options": {"ttl": "30m"}, "prompt_cache_retention": "24h", "prompt_cache_key": "synthetic-cache",
                        "tools": [{"type": "function", "name": "lookup", "parameters": {"type": "object"}, "defer_loading": True}],
                        "tool_choice": {"type": "allowed_tools", "mode": "auto", "tools": [{"type": "function", "name": "lookup"}]},
                        "reasoning": {"effort": "low", "context": "all_turns"}, "parallel_tool_calls": False,
                        **({"client_metadata": {"ws_request_header_x_openai_internal_codex_responses_lite": "true"}} if lite else {})}

            def verify(response):
                assert response["usage"] == USAGE
                if any(item.get("type") == "function_call" for item in response["output"]):
                    assert response["output"][0]["encrypted_content"] == ENCRYPTED_REASONING
                    assert [item["phase"] for item in response["output"] if item["type"] == "message"] == ["commentary", "partial_answer", "final_answer"]

            for lite in (False, True):
                for stream in (False, True):
                    status, raw = request(api + "/v1/responses", headers, {**fields(lite=lite), "stream": stream})
                    assert status == 200, (status, raw)
                    if stream:
                        response = next(json.loads(line[6:])["response"] for line in raw.decode().splitlines() if line.startswith("data: ") and '"response.completed"' in line)
                    else:
                        response = json.loads(raw)
                    verify(response)
                    if not stream:
                        status, raw = request(api + "/v1/responses", headers, {**fields(lite=lite), "stream": False, "input": [
                            *response["output"], {"type": "function_call_output", "call_id": "call_synthetic", "output": "7"}]})
                        assert status == 200, (status, raw)
                        verify(json.loads(raw))
                with connect(api.replace("http://", "ws://") + "/v1/responses", additional_headers=headers) as ws:
                    def turn(body):
                        ws.send(json.dumps({"type": "response.create", **body}))
                        while True:
                            event = json.loads(ws.recv(timeout=30))
                            assert event["type"] not in ("error", "response.failed")
                            if event["type"] == "response.completed":
                                verify(event["response"])
                                return event["response"]

                    first = turn(fields(lite=lite))
                    second = turn({**fields(lite=lite), "previous_response_id": first["id"], "input": [
                        {"type": "function_call_output", "call_id": "call_synthetic", "output": "7"}]})
                    turn({**fields(lite=lite), "input": [*second["output"], {"role": "user", "content": "reset"}]})
            # The execution lifecycle deliberately surfaces handshake rejection
            # without automatically generating over HTTP.
            status, raw = request(api + "/v1/responses", headers, {**fields("compat-fallback"), "stream": False})
            assert status == 200, (status, raw)
            verify(json.loads(raw))
            with connect(api.replace("http://", "ws://") + "/v1/responses", additional_headers=headers) as ws:
                ws.send(json.dumps({"type": "response.create", **fields("compat-fallback")}))
                try:
                    event = json.loads(ws.recv(timeout=30))
                    assert event["type"] in ("error", "response.failed")
                except ConnectionClosed:
                    pass
            assert stats() == {"http": 7, "websocket": 6, "fallback_handshake": 1}
            print("Codex compatibility flow passed: HTTP/SSE/WS, controls, opaque items, phases, usage, incremental tools, compaction reset and no automatic handshake retry.")
        except Exception:
            for name in (cpa, upstream):
                log = docker("logs", "--tail", "25", name, check=False)[-5000:]
                for secret in (key, management, "fake-compat-account"):
                    log = log.replace(secret, "[redacted]")
                print(name + ":\n" + log, file=sys.stderr)
            raise
        finally:
            for name in (cpa, upstream):
                docker("rm", "-f", name, check=False)
            docker("volume", "rm", volume, check=False)
            docker("network", "rm", network, check=False)


if __name__ == "__main__":
    mock() if "--mock" in sys.argv else main()
