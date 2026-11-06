"""Bounded SSE reader for isolated Docker tests; frames must contain only topics."""
import json, queue, socket, threading, time, urllib.request

class LiveStream:
    def __init__(self, url, headers=None, opener=None):
        self.frames = queue.Queue()
        self.response = (opener or urllib.request.build_opener()).open(urllib.request.Request(url, headers=headers or {}), timeout=25)
        assert self.response.status == 200
        assert self.response.headers['Content-Type'].startswith('text/event-stream')
        assert self.response.headers.get('X-Accel-Buffering') == 'no' or 'nginx' in self.response.headers.get('Server', '')
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
        self.wait('sync')

    def _read(self):
        try:
            for line in self.response:
                if line.startswith(b'data:'):
                    payload = json.loads(line[5:])
                    assert set(payload) == {'topics'}, 'SSE exposed data outside sanitized topic names'
                    assert set(payload['topics']) <= {'sync','usage','quota','accounts','clock'}
                    self.frames.put(payload['topics'])
        except (OSError, ValueError):
            pass

    def wait(self, topic, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if topic in self.frames.get(timeout=max(.01, deadline-time.monotonic())):
                    return
            except queue.Empty:
                break
        raise AssertionError('Missing SSE topic: '+topic)

    def close(self):
        try:
            self.response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        except (OSError, AttributeError):
            pass
        self.response.close()
        self.thread.join(timeout=2)
