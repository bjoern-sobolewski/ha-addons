"""Bounded terminal/usage probes of a disposable packaged proxy, never a live account."""

import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time


CASES = ("missing_details", "null_details", "zero_details", "cap_empty", "cap_nonzero", "failed", "failed_committed", "failed_auth", "cancelled")
MODES = ("http_json", "http_sse", "websocket", "websocket_native", "websocket_lite")


def mock():
    from aiohttp import web

    counts = {}

    def terminal(body):
        case = body["instructions"]
        counts[case] = counts.get(case, 0) + 1
        status = {"missing_details": "completed", "null_details": "completed", "zero_details": "completed", "cap_empty": "incomplete", "cap_nonzero": "incomplete", "failed_committed": "failed", "failed_auth": "failed"}.get(case, case)
        usage = {"input_tokens": 40, "output_tokens": 0 if case == "cap_empty" else 16}
        if case != "missing_details":
            usage.update({"input_tokens_details": {"cached_tokens": 8}, "output_tokens_details": {"reasoning_tokens": 0 if case == "cap_empty" else 8}})
        if case == "null_details":
            usage.update(input_tokens_details=None, output_tokens_details=None)
        if case == "zero_details":
            usage.update(input_tokens_details={"cached_tokens": 0}, output_tokens_details={"reasoning_tokens": 0})
        response = {"id": f"synthetic-response-{sum(counts.values())}", "status": status, "output": [], "usage": usage}
        if status == "completed":
            response["output"] = [{"type": "message", "id": "synthetic-message", "role": "assistant", "phase": "final_answer", "content": [{"type": "output_text", "text": "synthetic"}]}]
        if status == "incomplete":
            response["incomplete_details"] = {"reason": "max_output_tokens"}
        if status == "failed":
            response["error"] = {"type": "authentication_error" if case == "failed_auth" else "server_error", "message": "PRIVATE_SYNTHETIC_ERROR"}
        return {"type": "response." + status, "response": response}

    async def responses(request):
        # Match the proxy's existing synthetic upstream: no compression negotiation.
        socket = web.WebSocketResponse(compress=False)
        if socket.can_prepare(request).ok:
            await socket.prepare(request)
            async for message in socket:
                if message.type == web.WSMsgType.TEXT:
                    body = json.loads(message.data)
                    event = terminal(body)
                    if event["type"] != "response.failed" or body["instructions"] == "failed_committed":
                        await socket.send_json({"type": "response.created", "response": {"id": event["response"]["id"], "output": []}})
                    await socket.send_json(event)
            return socket
        body = await request.json()
        event = terminal(body)
        if body["instructions"] == "failed_committed":
            stream = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await stream.prepare(request)
            created = {"type": "response.created", "response": {"id": event["response"]["id"], "output": []}}
            await stream.write(("data: " + json.dumps(created) + "\n\n").encode())
            await stream.write(b'data: {"type":"response.output_text.delta","delta":"synthetic"}\n\n')
            await stream.write(("data: " + json.dumps(event) + "\n\n").encode())
            await stream.write_eof()
            return stream
        return web.Response(text="data: " + json.dumps(event) + "\n\n", content_type="text/event-stream")

    async def stats(_request):
        return web.json_response(counts)

    app = web.Application()
    app.router.add_route("*", "/responses", responses)
    app.router.add_get("/stats", stats)
    web.run_app(app, port=9000, print=None)


def run(args):
    # Reuse only the deployment's isolated Docker/startup helpers.
    sys.path.insert(0, str(Path(args.proxy_root).resolve() / "tests"))
    from smoke import docker, eventually, request
    from websockets.sync.client import connect
    import yaml

    prefix = "acp-terminal-probe-" + secrets.token_hex(4)
    network, volume = prefix + "-net", prefix + "-data"
    gateway, upstream = prefix + "-gateway", prefix + "-mock"
    bearer, management = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    results = []
    evidence = Path(args.output).resolve()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    # Do not overwrite earlier attempts.
    with evidence.open("x", encoding="utf-8") as output, tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        config = temporary / "config"
        config.mkdir()
        # Each deliberate failure gets a separate synthetic credential so normal
        # account cooldown cannot invalidate the following probe.
        aliases = [f"synthetic-{case}-{mode}" for case in CASES for mode in MODES]
        provider = {"api-keys": {"codex": [{"name": alias, "base-url": "http://mock:9000", "keys": [{"api-key": "fake-" + alias + str(index), "websockets": True} for index in range(2)], "models": [{"name": "gpt-6.1-sol", "alias": alias}]} for alias in aliases]}}
        provider["oauth"] = {"providers": {"codex": {"response-steering": args.duplex}}}
        provider["routing"] = {"retry": {"request-retry": 3, "max-retry-interval": 1}}
        (config / "providers.yaml").write_text(yaml.safe_dump(provider))
        (temporary / "options.json").write_text(json.dumps({"api_keys": [bearer], "management_key": management}))
        try:
            docker("network", "create", network)
            docker("volume", "create", volume)
            docker("run", "-d", "--name", upstream, "--network", network, "--network-alias", "mock", "-v", f"{Path(__file__).resolve().parent}:/test:ro", "python:3.13-alpine", "sh", "-c", "pip install -q aiohttp==3.13.3 && python /test/codex_terminal_flow.py --mock")

            def counts():
                return json.loads(docker("exec", upstream, "python", "-c", 'import urllib.request;print(urllib.request.urlopen("http://localhost:9000/stats").read().decode())'))

            eventually(lambda: counts() == {}, timeout=60)
            docker("create", "--init", "--name", gateway, "--network", network, "-v", volume + ":/data", "-v", f"{config}:/config:ro", "-p", "127.0.0.1::8080", args.image)
            docker("cp", str(temporary / "options.json"), gateway + ":/data/options.json")
            docker("start", gateway)
            api = "http://" + docker("port", gateway, "8080/tcp").splitlines()[0]
            headers = {"Authorization": "Bearer " + bearer}
            eventually(lambda: request(api + "/v1/models", headers)[0] == 200)
            for case in CASES:
                for mode in MODES:
                    events = []
                    failure = None
                    status = None
                    before = counts().get(case, 0)
                    body = {"model": f"synthetic-{case}-{mode}", "instructions": case, "input": [{"role": "user", "content": "synthetic"}], "max_output_tokens": 16, "reasoning": {"effort": "low"}}
                    if mode == "websocket_lite":
                        body["client_metadata"] = {"ws_request_header_x_openai_internal_codex_responses_lite": "true"}
                    started = time.perf_counter()
                    try:
                        if mode.startswith("websocket"):
                            socket_headers = {**headers, **({"originator": "codex_cli_rs", "User-Agent": "codex_cli_rs/0.159.0"} if mode != "websocket" else {})}
                            with connect(api.replace("http://", "ws://") + "/v1/responses", additional_headers=socket_headers, open_timeout=5) as socket:
                                if case == "failed_auth":
                                    # Establish a pinned continuation before a usage-bearing 401.
                                    socket.send(json.dumps({"type": "response.create", **body, "instructions": "missing_details"}))
                                    for _ in range(10):
                                        initial = json.loads(socket.recv(timeout=3))
                                        if initial.get("type") == "response.completed":
                                            body["previous_response_id"] = initial["response"]["id"]
                                            break
                                    else:
                                        raise AssertionError("Could not establish pinned continuation")
                                socket.send(json.dumps({"type": "response.create", **body}))
                                for _ in range(10):
                                    event = json.loads(socket.recv(timeout=3))
                                    events.append(event)
                                    if event.get("type") in ("response.completed", "response.incomplete", "response.failed", "response.cancelled", "error"):
                                        break
                                if case == "cancelled":
                                    # A cancelled turn must release the same socket for a reset.
                                    socket.send(json.dumps({"type": "response.create", **body, "instructions": "missing_details"}))
                                    for _ in range(10):
                                        following = json.loads(socket.recv(timeout=3))
                                        if following.get("type") == "response.completed":
                                            break
                                    else:
                                        raise AssertionError("No same-socket completion after cancellation")
                        else:
                            status, raw = request(api + "/v1/responses", headers, {**body, "stream": mode == "http_sse"})
                            events = [json.loads(line[6:]) for line in raw.decode().splitlines() if line.startswith("data: ") and line[6:] != "[DONE]"] if mode == "http_sse" and status == 200 else [json.loads(raw)]
                        if "PRIVATE_SYNTHETIC_ERROR" in json.dumps(events):
                            raise AssertionError("Private upstream error leaked")
                    except Exception as error:
                        failure = type(error).__name__
                    # Fixed fields only; never retain headers, errors, or output bodies.
                    known_codes = {"server_error", "upstream_error", "invalid_request_error", "stream_error", "timeout_error"}
                    receipts = [{"event": event.get("type"), "status": event.get("response", event).get("status"), "reason": event.get("response", event).get("incomplete_details"), "usage": event.get("response", event).get("usage"), "errorCode": event.get("error", {}).get("code") if event.get("error", {}).get("code") in known_codes else None, "errorType": event.get("error", {}).get("type") if event.get("error", {}).get("type") in known_codes else None} for event in events]
                    results.append({"case": case, "mode": mode, "httpStatus": status, "failure": failure, "latencyMs": round((time.perf_counter() - started) * 1000), "upstreamCalls": counts().get(case, 0) - before, "receipts": receipts})
                    print(json.dumps(results[-1]))
                    output.write(json.dumps(results[-1]) + "\n")
                    output.flush()
            if any(result["upstreamCalls"] != 1 for result in results):
                raise AssertionError("Invalid probe: expected one synthetic upstream generation per case")
            for result in results:
                assert result["failure"] is None, result
                terminals = [receipt for receipt in result["receipts"] if receipt["status"] in ("completed", "incomplete", "failed", "cancelled")]
                assert len(terminals) == 1, result
                receipt = terminals[0]
                expected_status = {"cap_empty": "incomplete", "cap_nonzero": "incomplete", "failed": "failed", "failed_committed": "failed", "failed_auth": "failed", "cancelled": "cancelled"}.get(result["case"], "completed")
                assert receipt["status"] == expected_status, result
                if expected_status == "incomplete":
                    assert receipt["reason"] == {"reason": "max_output_tokens"}, result
                if expected_status == "failed" and result["mode"].startswith("http"):
                    assert result["httpStatus"] != 200 or result["case"] == "failed_committed", result
                assert receipt["usage"]["input_tokens"] == 40, result
                assert receipt["usage"]["output_tokens"] == (0 if result["case"] == "cap_empty" else 16), result
                if result["case"] == "missing_details":
                    assert "input_tokens_details" not in receipt["usage"] and "output_tokens_details" not in receipt["usage"], result
                if result["case"] == "null_details":
                    assert receipt["usage"]["input_tokens_details"] is None and receipt["usage"]["output_tokens_details"] is None, result
                if result["case"] == "zero_details":
                    assert receipt["usage"]["input_tokens_details"]["cached_tokens"] == 0 and receipt["usage"]["output_tokens_details"]["reasoning_tokens"] == 0, result
                assert not any(receipt["event"] == "error" for receipt in result["receipts"]), result
        finally:
            for name in (gateway, upstream):
                docker("rm", "-f", name, check=False)
            docker("volume", "rm", volume, check=False)
            docker("network", "rm", network, check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--duplex", action="store_true")
    parser.add_argument("--proxy-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--image", default=os.environ.get("CPA_TEST_IMAGE", "ha-cpa-test:local"))
    parser.add_argument("--output", default=str(Path(__file__).resolve().parents[1] / ".test-data" / ("terminal-flow-" + secrets.token_hex(4) + ".jsonl")))
    arguments = parser.parse_args()
    if arguments.mock:
        mock()
    else:
        if not arguments.proxy_root or not arguments.output:
            parser.error("--proxy-root and --output are required")
        run(arguments)
