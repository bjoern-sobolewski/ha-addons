"""Local-only native voice probe; proxy credentials stay on this Python server.

Run with --sample <synthetic.wav> for an automated host-browser media probe,
or --microphone for a user-operated microphone check. No ACP actions/tools are
available in this diagnostic. It does not implement the ACP voice UI.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import tomllib
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path.home() / '.codex/config.toml')
    parser.add_argument('--base')
    parser.add_argument('--sample', type=Path)
    parser.add_argument('--microphone', action='store_true')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--port', type=int, default=8769)
    args = parser.parse_args()
    if not args.sample and not args.microphone:
        parser.error('Specify --sample or --microphone')
    config = tomllib.loads(args.config.read_text(encoding='utf-8'))
    provider = config['model_providers'][config['model_provider']]
    key = os.environ.get('CPA_VOICE_KEY') or provider['experimental_bearer_token']
    base = (args.base or provider['base_url'].removesuffix('/v1')).rstrip('/')
    nonce = secrets.token_urlsafe(24)
    calls = set()
    lock = threading.Lock()
    script = Path(__file__).with_name('voice_browser.cjs').read_text(encoding='utf-8')
    script = script.split('const result = await page.evaluate(async () => {', 1)[1].split('\n    });', 1)[0]
    script = script.replace('const events = []; let errorCode = null; let location = null; let setupStatus = null;', '''
      const events = []; let errorCode = null; let location = null; let setupStatus = null;
      window.stopVoiceTest = async () => {
        if(channel.readyState === 'open') channel.send(JSON.stringify({type:'session.close'}));
        channel.close(); microphone.getTracks().forEach(track=>track.stop()); peer.close();
        if(location) await fetch('/v1/realtime/calls/'+encodeURIComponent(location.split('/').pop())+'/hangup', {method:'POST',body:'{}'});
      };''')
    script = script.replace("fetch('/v1/", f"fetch('/{nonce}/v1/")
    if not args.microphone:
        script = script.replace('const microphone = await navigator.mediaDevices.getUserMedia({audio: true});', '''
      const audioContext = new AudioContext();
      const samples = await audioContext.decodeAudioData(await (await fetch('/sample.wav')).arrayBuffer());
      const destination = audioContext.createMediaStreamDestination();
      for (const delay of [4, 12]) {
        const source = audioContext.createBufferSource(); source.buffer = samples;
        source.connect(destination); source.start(audioContext.currentTime + delay);
      }
      const microphone = destination.stream;''')
        script = script.replace('peer.close();', 'peer.close(); await audioContext.close();')
    html = ('<!doctype html><meta charset="utf-8"><title>Native voice verification</title>'
            '<h1>Native voice verification</h1><p>This diagnostic has no ACP tools or action permissions.</p>'
            '<button id="start">Start bounded test</button> <button id="stop">Stop microphone and audio</button>'
            '<audio autoplay></audio><pre id="result">Ready</pre><script>'
            'document.querySelector("#stop").onclick=()=>window.stopVoiceTest?.();'
            'document.querySelector("#start").onclick=async()=>{document.querySelector("#start").disabled=true;'
            'document.querySelector("#result").textContent="Testing for up to 30 seconds…";'
            'try{const result=await(async()=>{' + script + '})();'
            'document.querySelector("#result").textContent=JSON.stringify(result,null,2);'
            'await fetch("/result",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(result)});'
            '}catch(e){document.querySelector("#result").textContent="Probe failed: "+e.name;}'
            'finally{document.querySelector("#start").disabled=false;}};</script>').encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, body, content_type='application/json', location=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            if location:
                self.send_header('Location', location)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/':
                self.send(200, html, 'text/html; charset=utf-8')
            elif self.path == '/sample.wav' and args.sample:
                self.send(200, args.sample.read_bytes(), 'audio/wav')
            else:
                self.send(404, b'{}')

        def do_POST(self):
            if self.headers.get('Origin') != 'http://127.0.0.1:' + str(args.port):
                self.send(403, b'{}')
                return
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 256 * 1024:
                self.send(413, b'{}')
                return
            body = self.rfile.read(length)
            if self.path == '/result':
                result = json.loads(body)
                # Only the bounded probe's numeric/boolean status fields and event names.
                print(json.dumps(result), flush=True)
                if args.once:
                    threading.Timer(1, server.shutdown).start()
                self.send(200, b'{}')
                return
            path = self.path.removeprefix('/' + nonce)
            if path == self.path or (path != '/v1/live' and not path.endswith('/hangup')):
                self.send(404, b'{}')
                return
            if path.endswith('/hangup'):
                with lock:
                    if path.split('/')[-2] not in calls:
                        self.send(404, b'{}')
                        return
            request = urllib.request.Request(base + path, data=body, headers={
                'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0',
                'OpenAI-Alpha': 'quicksilver=v2'}, method='POST')
            try:
                try:
                    response = urllib.request.urlopen(request, timeout=32)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    location = response.headers.get('Location')
                    if path == '/v1/live' and location:
                        with lock:
                            calls.add(location.split('/')[-1])
                    self.send(response.status, response.read(1 << 20), response.headers.get('Content-Type', 'text/plain'), location)
            except OSError:
                self.send(502, b'{"error":{"code":"probe_transport_error"}}')

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Ready: http://127.0.0.1:{args.port} (credentials remain server-side)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
