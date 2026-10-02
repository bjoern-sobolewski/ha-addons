"""A deterministic OpenAI-compatible test provider; no external requests."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200)
        if request.get('stream'):
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for delta, finish in (({'role': 'assistant', 'content': 'ok'}, None), ({}, 'stop')):
                chunk = {'id': 'test-stream', 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': 'test-model', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}}
                self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n')
            return
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'id': 'test-response', 'object': 'chat.completion', 'created': int(time.time()), 'model': 'test-model', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'ok'}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}}).encode())


HTTPServer(('0.0.0.0', 9000), Handler).serve_forever()
