// Synthetic WebRTC probe. The server attaches credentials; the browser never receives them.
const {chromium} = require('/test/node_modules/playwright');
const http = require('node:http');

(async () => {
  const baseURL = process.env.CPA_VOICE_BASE;
  const apiKey = process.env.CPA_VOICE_KEY;
  if (!baseURL || !apiKey) throw Error('Set CPA_VOICE_BASE and CPA_VOICE_KEY on the probe server');
  const server = http.createServer(async (request, response) => {
    if (request.url === '/') {
      response.setHeader('Content-Type', 'text/html');
      response.end('<!doctype html><title>Synthetic voice connectivity probe</title><audio autoplay></audio>');
      return;
    }
    try {
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      const upstream = await fetch(baseURL + request.url, {
        method: 'POST', headers: {Authorization: 'Bearer ' + apiKey, 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'},
        body: Buffer.concat(chunks), signal: AbortSignal.timeout(30000),
      });
      response.writeHead(upstream.status, {'Content-Type': upstream.headers.get('content-type') || 'text/plain', Location: upstream.headers.get('location') || ''});
      response.end(Buffer.from(await upstream.arrayBuffer()));
    } catch {
      response.writeHead(502); response.end('Probe transport unavailable');
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_EXECUTABLE, args: [
    '--no-sandbox', '--autoplay-policy=no-user-gesture-required', '--use-fake-ui-for-media-stream',
    '--use-fake-device-for-media-stream', '--use-file-for-fake-audio-capture=/samples/phrase.wav',
  ]});
  try {
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:' + server.address().port);
    const result = await page.evaluate(async () => {
      const peer = new RTCPeerConnection();
      const microphone = await navigator.mediaDevices.getUserMedia({audio: true});
      microphone.getTracks().forEach(track => peer.addTrack(track, microphone));
      const channel = peer.createDataChannel('oai-events');
      const events = []; let errorCode = null; let location = null; let setupStatus = null;
      channel.onmessage = ({data}) => {
        try {
          const event = JSON.parse(data); events.push(event.type);
          if (event.type === 'error') errorCode = event.error?.code || 'upstream_error';
          if (event.type === 'delegation.created' && event.item?.id) channel.send(JSON.stringify({
            type: 'delegation.context.append', delegation_item_id: event.item.id,
            content: [{type: 'input_text', text: 'The connectivity test heard your phrase. No actions were performed.'}],
          }));
        } catch {}
      };
      peer.ontrack = ({streams}) => {document.querySelector('audio').srcObject = streams[0];};
      try {
        await peer.setLocalDescription(await peer.createOffer());
        await Promise.race([new Promise(resolve => {
          if (peer.iceGatheringState === 'complete') resolve();
          else peer.onicegatheringstatechange = () => {if (peer.iceGatheringState === 'complete') resolve();};
        }), new Promise(resolve => setTimeout(resolve, 6000))]);
        const response = await fetch('/v1/live', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
          sdp: peer.localDescription.sdp, session: {model: 'gpt-live-1-codex', instructions: 'Respond briefly. Do not use tools or perform actions.',
            audio: {output: {voice: 'marin'}}, delegation: {type: 'client'}},
        })});
        setupStatus = response.status; location = response.headers.get('location');
        if (!response.ok) return {setupStatus, mediaVerified: false};
        await peer.setRemoteDescription({type: 'answer', sdp: await response.text()});
        await new Promise(resolve => setTimeout(resolve, 16000));
        let receivedBytes = 0, sentBytes = 0;
        (await peer.getStats()).forEach(stat => {
          if (stat.type === 'inbound-rtp' && stat.kind === 'audio') receivedBytes += stat.bytesReceived || 0;
          if (stat.type === 'outbound-rtp' && stat.kind === 'audio') sentBytes += stat.bytesSent || 0;
        });
        return {setupStatus, state: peer.connectionState, channel: channel.readyState, sentBytes, receivedBytes,
          events: [...new Set(events)], errorCode, mediaVerified: sentBytes > 0 && receivedBytes > 0};
      } finally {
        if (channel.readyState === 'open') channel.send(JSON.stringify({type: 'session.close'}));
        channel.close(); microphone.getTracks().forEach(track => track.stop()); peer.close();
        if (location) {
          const callID = location.split('/').pop();
          const stopped = await fetch('/v1/realtime/calls/' + encodeURIComponent(callID) + '/hangup', {method: 'POST', body: '{}'});
          console.log('hangup status', stopped.status);
        }
      }
    });
    console.log(JSON.stringify(result));
  } finally {
    await browser.close(); await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error('Voice probe failed:', error.name); process.exitCode = 1;});
