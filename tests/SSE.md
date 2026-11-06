# Live stats checks

Keeper exposes authenticated GET /api/v1/live; CPA exposes private GET /v8/management/live. Frames contain invalidation topics only. Each frontend shares one connection and coalesces local API reads; reconnect starts with sync. Existing role-scoped endpoints serialize values. Streams, cache reads and the rolling-window clock do not invoke provider quota/reset APIs.

Keeper cache updates batch for 250 ms; SSE writes batch for 150 ms and client reads for 200 ms. Usage ingestion, existing rollup batching and history persistence retain their backend scheduling. Charts retain their query identity and animate dataset updates without replaying the initial render.

Build the packaged images, which run frontend and backend suites:

    docker buildx build --load -t ha-cpa-sse:local cliproxyapi
    docker buildx build --load -t ha-keeper-sse:local cpa-usage-keeper

Run the isolated integration suite (Python dependencies: pyyaml and websockets):

    CPA_QUOTA_IMAGE=ha-cpa-sse:local KEEPER_QUOTA_IMAGE=ha-keeper-sse:local python tests/quota_flow.py

The quota flow opens management, API-key viewer and read-only SSE streams, checks gateway restrictions, observes HTTP/WebSocket quota changes, success/failure totals, reconnect synchronization, and confirms cached reads plus open streams do not increase mock provider traffic. It uses synthetic credentials and removes its containers, network and data volumes on exit.

Build the browser runner and include the real Chromium checks:

    docker buildx build --load -f tests/Dockerfile.sse-browser -t ha-sse-browser:local .
    SSE_BROWSER=1 CPA_QUOTA_IMAGE=ha-cpa-sse:local KEEPER_QUOTA_IMAGE=ha-keeper-sse:local python tests/quota_flow.py

Browser checks cover all Keeper reporting tabs, credential volume bars and the open account popup, CPAMC dashboard and provider graphs, preserved chart/bar DOM nodes, mobile overflow, and idle provider traffic. Screenshots and browser results are written under ignored .test-data/sse-20261106/browser.
