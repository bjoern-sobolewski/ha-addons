# Voice integration

Voice is a server-side ACP integration. This add-on does not implement the ACP
`/ai-assist` user interface. Use the same API gateway and Bearer authentication
as Responses, exclusively from the ACP server. Never send the proxy key or a
provider OAuth token to a browser. No additional paid provider is needed for
the two explicit Codex audio models below. These are proxy selectors, not
claims about the underlying transcription or speech model.

## Dictation

`POST /v1/audio/transcriptions`, `Content-Type: multipart/form-data`:

| Field | Value |
| --- | --- |
| `file` | One completed recording; original filename must have a supported extension |
| `model` | `codex-transcribe` (optional) |
| `language` | Optional lowercase ISO-639-1 code, e.g. `en` or `de` |
| `response_format` | `json` (default), or `text` |

JSON success: `{"text":"The recognized words."}`. Text mode returns UTF-8
`text/plain`. The result is editable prompt text; dictation never submits a
Responses request, executes a tool, or changes conversation history itself.

Accepted recordings: WAV, WebM (including browser MediaRecorder WebM/Opus),
MP3, Ogg/Opus, FLAC, MP4/M4A. Extension and container signature are checked;
FFmpeg must successfully decode the audio. The complete multipart body is
limited to 16 MiB; decoded audio must be between 100 ms and 120 seconds.
The recording remains in memory and is forwarded with its audio MIME type.
There is no file spooling or local audio retention. Upstream retention is
governed by the selected account's service policies; the proxy returns no
upstream asset references.

Limits: four simultaneous audio requests, 15 seconds for upload/decoding,
60 seconds total execution, and an 8 MiB upstream response. Close/abort the
request to cancel. For MediaRecorder, stop the recorder and combine its chunks
into one completed container before uploading; individual arbitrary chunks
may not be independently decodable. Unsupported `prompt`, streaming,
timestamp, and diarization options are rejected explicitly.

## Read aloud

`POST /v1/audio/speech`, `Content-Type: application/json`:

```json
{"model":"codex-speech","input":"Text from the existing assistant response.","response_format":"aac","voice":"default"}
```

Success is binary ADTS AAC with `Content-Type: audio/aac`. `input` must contain
1â€“4096 characters. Format and voice may be omitted; only AAC and the upstream
default voice are supported. Speed and instruction overrides are rejected.
An ACP server can stream the returned bytes to a browser audio element and
discard the response afterward. Stop playback locally and abort pending
generation when the user chooses Stop. Identify generated speech in the UI.

Existing speech selectors keep their existing provider behavior. In
particular, `tts-1`, `gpt-4o-mini-tts`, and `grok-tts` retain the existing xAI
route. ACP must explicitly request `codex-speech` to use ChatGPT OAuth.
Do not infer subscription support from the existence of `/audio/speech`.

## Codex desktop voice

Codex desktop creates its native WebRTC media call using the desktop's saved
ChatGPT login, then attaches app-server control through the configured provider
at `GET /v1/live/{call_id}`. The proxy accepts these externally created native
calls with an ordinary client Bearer key. The same ChatGPT account must also be
connected to the proxy as an eligible Codex OAuth account. Set the top-level Codex setting
`experimental_realtime_ws_base_url = "http://proxy-host:8080/v1"` to the same
base as the inference provider: this desktop version otherwise sends the control
socket directly to OpenAI even when a custom inference provider is configured.
Keep the existing provider and file-based Bearer key. A proxy client key
does not supply a desktop login or grant a subscription voice entitlement.

Before relaying any control events, the proxy matches the call against at most
eight eligible OAuth accounts. Only an upstream missing-call 404 permits trying
another account. Authentication, quota and network errors stop discovery. Scoped
Realtime client secrets cannot attach to externally created calls. Existing
proxy-created call ownership remains enforced; completed call IDs are remembered
for two hours in this process, with a bounded history that fails closed when full.
Home-backed external-call discovery is unsupported; existing Home-created calls
retain their normal path.

The control attachment shares the eight-session limit, 30-second setup deadline,
15-minute absolute lifetime, bounded WebSocket relay and shutdown cleanup.
Desktop audio travels directly over WebRTC between the client and OpenAI; the
proxy carries the control/delegation connection. Stop closes both client media
and the control session. This does not add microphone access or action execution
to the proxy.

## Native live voice

The existing native Codex WebRTC path is `POST /v1/live` (also
`POST /v1/realtime/calls`). Send a JSON SDP offer and native session:

```json
{
  "sdp":"v=0\r\n...",
  "session":{
    "model":"gpt-live-1-codex",
    "instructions":"Use the ACP server for authorized actions.",
    "audio":{"output":{"voice":"marin"}},
    "delegation":{"type":"client"}
  }
}
```

Create an audio send/receive WebRTC peer and an `oai-events` data channel before
creating the offer. The ACP server attaches the Bearer key and forwards the
offer; the browser receives the SDP answer and call identifier. Successful
setup returns an SDP answer and a `Location` identifying the call. The proxy
adds the native `OpenAI-Alpha: quicksilver=v2` header when none is supplied.
This native protocol differs from the public Realtime protocol.

Native events include `session.started`, `session.updated`,
`input_transcript.added`, `output_transcript.added`, `turn.done`,
`output_audio.delta`, and `delegation.created`. A native delegation result is
`{"type":"delegation.context.append","delegation_item_id":"...","content":[{"type":"input_text","text":"Authorized ACP result"}]}`.
Only the ACP server may perform the underlying work, with its existing
permissions, tool allowlist, history, and action confirmations. Never execute
an upstream-requested action directly in a browser or in this proxy.

WebRTC carries Opus audio and handles playback; it does not carry a WebM file.
The native WebSocket variant uses base64 mono PCM16 at 24 kHz:
`GET /v1/realtime?model=gpt-live-1-codex` selects the native `/v1/live` upstream.
The proxy supplies `OpenAI-Alpha: quicksilver=v2` for this native WebSocket
handshake; standard Realtime model transports keep their existing headers.
Client messages include `session.update`, `input_audio.append`,
`session.context.append`, `delegation.context.append`, and `session.close`.
The standard Realtime model selectors retain their existing transport.
Do not mix native event names with standard `input_audio_buffer.append`,
`response.cancel`, or `conversation.item.truncate` without a protocol adapter.

Provide explicit Start/Stop controls. Stop microphone tracks, close data
channels and peer connections, abort pending requests, and have the ACP
server POST `/v1/realtime/calls/{call_id}/hangup`. The existing call-sideband
routes pin credentials and enforce the creating API principal. Sessions have
an absolute 15-minute lifetime (reconnecting does not extend it), a maximum
of eight setups/active sessions, 30-second setup deadline, 256 KiB WebSocket
message limit, and bounded WebSocket writes/handshakes. Server shutdown
closes local session resources. Media relay limits additionally apply when
the optional existing relay is enabled.

Cloudflare HTTP/WebSocket routing does not transport WebRTC media. ICE,
UDP/TCP reachability, NAT and potentially an existing TURN service determine
media connectivity. Do not enable public management, open ports, introduce
a TURN service, or change tunnel settings just to make signaling return 201.

Native upstream audio, voice activity detection, interruption behavior, and
subscription access require live verification on the selected account and
network. A 201 SDP answer or a WebSocket 101 is insufficient proof. The
synthetic browser probe in `tests/voice_browser.cjs` distinguishes signaling
from sent/received audio bytes; it is not an ACP UI or a microphone test.

Realtime transcription-only sessions remain unsupported by the existing
Codex adapter. That restriction does not apply to the separate dictation
endpoint. If native live voice is denied or media cannot connect, the
smallest alternative uses ACP-side voice activity detection to submit short
recordings to dictation, sends their editable/confirmed text through the
existing Responses integration, and plays `codex-speech` output. Interruption
then stops playback and cancels the ACP request. This alternative needs ACP
implementation and has turn-based latency; do not present it as verified
native live voice.

## Errors and privacy

Failures use `{"error":{"type":"audio_error","code":"...","message":"..."}}`.
Typical statuses: 400 malformed/invalid/duration/options, 401 invalid proxy
authentication, 413 upload too large, 415 unsupported container, 429
concurrency/upstream quota, 501 unsupported upstream capability, 502 upstream
authentication/access/transport/invalid response, 503 no eligible OAuth
credential or decoder, 504 execution timeout. Cancellation stops upstream
work; disconnected clients may not receive a final error response.

Audio routes bypass request/error body capture, including when request logging
is enabled. Native audio requests reuse the OAuth scheduler, refresh lifecycle,
per-account transports, cancellation, Home routing and rate-limit handling.
Raw provider failures and upstream transcription asset identifiers are not
returned by the new audio endpoints. Do not log recordings, transcripts,
speech input, session event payloads, or credentials in ACP request logs.

## ACP work still required

Add recording permission UX, Start/Stop/Cancel, an editable dictation draft,
server-side multipart forwarding, AAC playback, and the native session bridge.
Enforce session ownership at the ACP user level even if ACP uses one shared
proxy key. Relay action requests through existing authorization and
confirmation paths. Handle voice activity and interruption using the chosen
protocol; verify actual audio and barge-in before advertising live voice.

The investigated desktop uses multipart `/backend-api/transcribe` returning
`text`, and POST `/backend-api/read-aloud/synthesize` with `{"text":"..."}`
returning AAC. These backend endpoints are private implementation contracts,
not stable public API guarantees. Public compatibility reference:
[OpenAI transcription API](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create).

## Verification recorded 2026-11-10

The deployment image passed Go voice/media and middleware tests, go vet,
existing proxy/auth/Responses suites, wrapper checks and isolated Docker HTTP,
WebSocket, quota-routing, persistence and shutdown checks. With an existing
local ChatGPT OAuth login, real WAV and WebM/Opus dictation recognized a known
synthetic phrase. Native AAC output decoded successfully and a transcription
round trip reproduced the supplied words. No API key was introduced.

The native call returned HTTP 201 in both a container Chromium probe and a
host-browser synthetic audio probe. Both then failed ICE connectivity with
zero sent/received audio bytes and no open data channel. Direct native
WebSocket session configuration was rejected with `forbidden` for the tested
OAuth login. These observations do not establish that every subscription is
unsupported, or identify a specific firewall/NAT cause. Native bidirectional
audio, live speech detection and interruption remain unverified.

For a user-operated microphone test, run this from the repository:

```sh
python tests/voice_harness.py --base https://YOUR-PROXY-HOST --microphone
```

Open `http://127.0.0.1:8769`, choose Start and grant microphone permission.
The Python server reads the existing file bearer from the selected Codex
provider; credentials stay on that server. The test is bounded and Stop closes
the microphone/peer and requests hangup. This diagnostic has no ACP tools and
cannot establish that ACP authorization or its voice UI has been integrated.
