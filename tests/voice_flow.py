"""Exercise the deployment image with disposable tmpfs configuration and credentials.

Optional real probe: CPA_VOICE_OAUTH_FILE points to an existing Codex auth.json;
CPA_VOICE_SAMPLE is a synthetic WAV and CPA_VOICE_EXPECTED is its known phrase.
The original auth file is never mounted or modified. Only its short-lived access
token is copied into container tmpfs; refresh tokens are not copied.
"""
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import wave

IMAGE = os.environ.get('CPA_TEST_IMAGE', 'ha-cpa-voice:local')


def docker(*arguments, input=None):
    result = subprocess.run(['docker', *arguments], input=input, capture_output=True, check=True)
    return result.stdout


def request(base, path, key=None, body=None, content_type='application/json'):
    headers = {'Content-Type': content_type}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(base + path, data=body, headers=headers, method='POST' if body is not None else 'GET')
    try:
        response = urllib.request.urlopen(req, timeout=65)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


def recording(audio, filename):
    boundary = 'voice-' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\ncodex-transcribe\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode() + audio + f'\r\n--{boundary}--\r\n'.encode()
    return body, 'multipart/form-data; boundary=' + boundary


def silence():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(24000)
        writer.writeframes(bytes(48000))
    return buffer.getvalue()


def main():
    name = 'ha-cpa-voice-' + secrets.token_hex(4)
    key = secrets.token_urlsafe(32)
    options = {'api_key_source': 'management_ui', 'api_keys': [key], 'management_key': secrets.token_urlsafe(32)}
    fixtures = {'options': options}
    real = os.environ.get('CPA_VOICE_OAUTH_FILE')
    if real:
        tokens = json.loads(Path(real).read_text(encoding='utf-8'))['tokens']
        fixtures['auth'] = {'type': 'codex', 'access_token': tokens['access_token'], 'account_id': tokens['account_id']}
    try:
        docker('run', '-d', '--init', '--name', name, '--tmpfs', '/data:rw,noexec,nosuid,size=64m',
               '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', '-p', '127.0.0.1::8080', '-p', '127.0.0.1::8317',
               '--entrypoint', 'sh', IMAGE, '-c', 'while [ ! -f /data/ready ]; do sleep .1; done; exec /opt/ha/run.sh')
        installer = ('import json,sys,pathlib; f=json.load(sys.stdin); p=pathlib.Path("/data"); '
                     '(p/"options.json").write_text(json.dumps(f["options"])); (p/"auth").mkdir(mode=0o700); '
                     '[(p/"auth"/"voice-test.json").write_text(json.dumps(f["auth"])) for _ in [0] if "auth" in f]; '
                     '(p/"ready").touch()')
        docker('exec', '-i', name, 'python3', '-c', installer, input=json.dumps(fixtures).encode())
        port = docker('port', name, '8080').decode().strip().split(':')[-1]
        base = 'http://127.0.0.1:' + port
        for _ in range(60):
            try:
                if request(base, '/v1/models', key)[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(.5)
        else:
            raise AssertionError('Container did not become ready')
        temporary_baseline = docker('exec', name, 'sh', '-c', 'find /tmp -type f | sort')
        for endpoint in ['/v1/audio/transcriptions', '/v1/audio/speech', '/v1/live']:
            assert request(base, endpoint, body=b'{}')[0] == 401
            assert request(base, endpoint, 'invalid', b'{}')[0] == 401
        for audio, filename, expected in [(b'', 'a.wav', 400), (b'not an audio file', 'a.exe', 415),
                                          (b'RIFF0000WAVEbad', 'a.wav', 400), (bytes(16 << 20), 'a.wav', 413)]:
            body, content_type = recording(audio, filename)
            assert request(base, '/v1/audio/transcriptions', key, body, content_type)[0] == expected
        assert request(base, '/v1/audio/transcriptions', key, b'--broken', 'multipart/form-data; boundary=x')[0] == 400
        speech = json.dumps({'model': 'codex-speech', 'input': 'A short test.', 'response_format': 'mp3'}).encode()
        assert request(base, '/v1/audio/speech', key, speech)[0] == 400
        assert request(base, '/v1/realtime/transcription_sessions', key, b'{}')[0] == 501
        print('PASS: container authentication, upload limits, malformed input and unsupported formats/options')
        sample = Path(os.environ['CPA_VOICE_SAMPLE']).read_bytes() if real else silence()
        body, content_type = recording(sample, 'phrase.wav')
        status, _, transcript = request(base, '/v1/audio/transcriptions', key, body, content_type)
        if not real:
            assert status == 503
            speech = json.dumps({'model': 'codex-speech', 'input': 'A short test.'}).encode()
            assert request(base, '/v1/audio/speech', key, speech)[0] == 503
            print('PASS: missing OAuth cannot fall back to a paid provider')
        else:
            expected = os.environ['CPA_VOICE_EXPECTED'].lower()
            assert status == 200 and expected in json.loads(transcript)['text'].lower(), 'Real WAV transcription failed'
            webm = docker('exec', '-i', name, 'ffmpeg', '-v', 'error', '-i', 'pipe:0', '-c:a', 'libopus', '-f', 'webm', 'pipe:1', input=sample)
            body, content_type = recording(webm, 'recording.webm')
            status, _, transcript = request(base, '/v1/audio/transcriptions', key, body, content_type)
            assert status == 200 and expected in json.loads(transcript)['text'].lower(), 'Real WebM transcription failed'
            speech = json.dumps({'model': 'codex-speech', 'input': os.environ['CPA_VOICE_EXPECTED'], 'response_format': 'aac'}).encode()
            status, headers, spoken = request(base, '/v1/audio/speech', key, speech)
            assert status == 200 and headers['Content-Type'] == 'audio/aac'
            decoded = docker('exec', '-i', name, 'ffmpeg', '-v', 'error', '-i', 'pipe:0', '-f', 'wav', 'pipe:1', input=spoken)
            assert len(decoded) > 1000, 'Speech was not playable'
            # Round-trip recognition verifies supplied words without requiring a listener.
            body, content_type = recording(decoded, 'spoken.wav')
            status, _, transcript = request(base, '/v1/audio/transcriptions', key, body, content_type)
            assert status == 200 and expected in json.loads(transcript)['text'].lower(), 'Speech content round trip failed'
            print('PASS: real OAuth WAV/WebM dictation and playable AAC with accurate speech round trip')
            if os.environ.get('CPA_VOICE_BROWSER'):
                browser_env = {**os.environ, 'CPA_VOICE_KEY': key, 'CPA_VOICE_BASE': 'http://host.docker.internal:' + port}
                result = subprocess.run(['docker', 'run', '--rm', '-e', 'CPA_VOICE_KEY', '-e', 'CPA_VOICE_BASE',
                                         '-v', str(Path(__file__).resolve().parent) + ':/scripts:ro',
                                         '-v', str(Path(os.environ['CPA_VOICE_SAMPLE']).resolve()) + ':/samples/phrase.wav:ro',
                                         'ha-sse-browser:local', '/scripts/voice_browser.cjs'], env=browser_env, capture_output=True, text=True, timeout=65)
                print(result.stdout.strip())
                assert result.returncode == 0, 'Synthetic browser probe failed'
        assert docker('exec', name, 'sh', '-c', 'find /tmp -type f | sort') == temporary_baseline, 'Temporary file leak'
        docker('stop', '-t', '12', name)
        print('PASS: no temporary audio files; graceful container shutdown')
    finally:
        docker('rm', '-f', name)


if __name__ == '__main__':
    main()
