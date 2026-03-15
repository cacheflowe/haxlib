# WebRTC Video Streaming — TD → Browser

Streams a TouchDesigner output to one or more browser tabs via WebRTC, using the Oversite WebSocket server as the signaling channel. No media passes through the server — only the handshake. Video flows peer-to-peer between TD and each browser.

## Files

| File | Role |
|---|---|
| `WebRTCVideoOut.py` | TD Python extension — manages connections, drives signaling |
| `webrtc-stream.js` | Browser web component — receives stream, renders video |
| `webrtc.html` | Demo page |

---

## How WebRTC works

WebRTC lets two peers (here: TouchDesigner and a browser tab) stream media directly to each other without routing video through a server. On a local network no STUN/TURN relay server is needed.

Before video can flow, the two peers need to agree on codec parameters and find each other's network address. This negotiation is called **signaling** and has two phases:

### 1. Offer / Answer (SDP)

SDP (Session Description Protocol) is a text format that describes what a peer wants to send and how — codecs, resolution, track IDs, etc.

1. TD calls `createOffer()` — the WebRTC DAT generates an SDP offer and fires `onOffer`.
2. TD sends the offer SDP to the browser via WebSocket.
3. The browser sets it as the remote description, generates an SDP answer, and sends it back.
4. TD sets the answer as its remote description. Both sides now agree on the media format.

### 2. ICE candidates (network discovery)

ICE (Interactive Connectivity Establishment) is how the peers find a usable network path to each other.

After the SDP exchange each side generates a list of **ICE candidates** — possible network addresses and ports (local IP, public IP via STUN, relay via TURN). They exchange these candidates over the signaling channel. Once a matching pair is found, the direct peer connection is established and video starts flowing.

On a LAN the peers typically connect on their first local-network candidate within milliseconds.

### Why a signaling server is needed at all

WebRTC is peer-to-peer for media, but the peers still need some out-of-band channel to exchange the offer/answer and ICE candidates before they can reach each other directly. Any reliable message channel works — in this case, Oversite's existing WebSocket server.

---

## How signaling piggybacks on Oversite

Oversite's WebSocket server handles a pub/sub store across all connected clients. Each client connects with a `sender` ID (stable per device/page, e.g. `tablet_ui`) and a `channel`.

Two message types carry signaling:

**AppStore key/value** (`store: true, sendOnly: true`) — used for `webrtc_request` and `webrtc_disconnect`. The `sendOnly` flag tells the server to route the message without persisting it or re-broadcasting it to newly-connected clients.

**`broadcastCustomJson`** — sends arbitrary JSON to all clients on the channel (or to a specific `receiver`). Used for Offer / Answer / ICE signals. The `<webrtc-stream>` component listens via `_store.addListener(this, 'custom_json')`.

### Two IDs, two purposes

| Field | Set by | Value example | Purpose |
|---|---|---|---|
| `ws_sender` | `<app-store-init sender="...">` | `tablet_ui` | Stable device identity; server uses it to route messages to the right WebSocket client |
| `viewerId` | `<webrtc-stream webrtc-id="...">` | `webrtc_viewer_a3f2k` | Unique per component instance; used to filter incoming signals in the browser so each component only processes its own Offer/ICE |

The `ws_sender` is intentionally stable across tabs and refreshes — it identifies the device, not the session. The `viewerId` is auto-generated per component if the `webrtc-id` attribute is not set.

### Message format

Oversite uses the [TouchDesigner Signaling API](https://docs.derivative.ca/Palette:signalingServer#Signaling_API) JSON schema:

```json
{
  "metadata": { "apiVersion": "1.0.1", ... },
  "signalingType": "Offer" | "Answer" | "Ice",
  "sender": "td_webrtc",
  "receiver": "tablet_ui",
  "viewerId": "webrtc_viewer_a3f2k",
  "content": { "sdp": "..." }
}
```

`receiver` routes the message to the correct WebSocket client. `viewerId` lets the browser-side component filter signals that belong to it — important when multiple `<webrtc-stream>` instances share a page or when the same `sender` is used across tabs.

---

## Full connection sequence

```
Browser tab loads
  └─ <webrtc-stream> storeIsReady():
       └─ auto-generates webrtc-id attribute if absent (e.g. "webrtc_viewer_a3f2k")
            └─ _store.set("webrtc_request", "webrtc_viewer_a3f2k", sendOnly=true)
                 └─ WS → server → TD  (not stored, not re-broadcast to future clients)

TD OnReceiveText: key="webrtc_request", value="webrtc_viewer_a3f2k", sender="tablet_ui"
  └─ Connect("webrtc_viewer_a3f2k", ws_sender="tablet_ui"):
       openConnection()        → new conn_id UUID
       addTrack(conn_id, 'video_track_1', 'video')
       createOffer(conn_id)    → triggers OnOffer callback

TD OnOffer fires
  └─ setLocalDescription(conn_id, 'offer', sdp)
       └─ sendText → receiver="tablet_ui", viewerId="webrtc_viewer_a3f2k"
            └─ server routes to all WS clients with sender="tablet_ui"

Browser custom_json: signalingType="Offer", viewerId="webrtc_viewer_a3f2k"
  └─ viewerId matches this._viewerId → this component handles it
       └─ setRemoteDescription(offer sdp)
            └─ createAnswer()
                 └─ setLocalDescription(answer)
                      └─ broadcastCustomJson → {signalingType:"Answer", viewerId:"webrtc_viewer_a3f2k"}

TD OnReceiveText: signalingType="Answer", viewerId="webrtc_viewer_a3f2k"
  └─ connections["webrtc_viewer_a3f2k"] → conn_id
       └─ setRemoteDescription(conn_id, 'answer', sdp)

ICE candidates exchange (both directions, concurrently with above)
  └─ TD OnIceCandidate → sendText (receiver="tablet_ui", viewerId="webrtc_viewer_a3f2k")
  └─ Browser onicecandidate → broadcastCustomJson {signalingType:"Ice", viewerId:"webrtc_viewer_a3f2k"}

ICE pair found → peer connection established → video flows
  └─ Browser ontrack fires → video element plays

Tab closes / component removed
  └─ beforeunload + disconnectedCallback:
       └─ _store.set("webrtc_disconnect", "webrtc_viewer_a3f2k", sendOnly=true)
            └─ TD: Disconnect("webrtc_viewer_a3f2k") → closeConnection(conn_id)
```

---

## Multi-viewer architecture

Each `<webrtc-stream>` component gets its own WebRTC peer connection. TD maintains three dicts keyed consistently around the separation between routing (ws_sender) and identification (viewer_id):

- `connections`: `viewer_id → conn_id` — looks up a connection when a signaling message arrives
- `connection_ws_senders`: `conn_id → ws_sender` — target address for routing Offer/ICE back to the browser
- `connection_viewer_ids`: `conn_id → viewer_id` — echoed in outgoing Offer/ICE so the browser component can filter

For video delivery, a **Replicator COMP** inside the Base COMP watches an `active_streams` Table DAT and spawns one VideoStreamOut TOP per connected viewer. Each replicated TOP's "WebRTC Connection" parameter is an expression that reads its connection ID from the table. The Replicator reacts to connection state changes — a row is added only when a connection reaches `connected`, ensuring the TOP isn't created before the peer connection is live.

### Why `sendOnly: true` matters

Without it, the server persists `webrtc_request` in its store. When a second tab connects, the server syncs all stored state to the new client — including replaying the first tab's `webrtc_request` to TD. TD would call `Connect()` again for the first tab's viewer_id, closing its existing connection and starting a new negotiation. `sendOnly: true` prevents this by keeping the key out of the store entirely.

### Why `client_disconnected` is not used

Oversite broadcasts `client_disconnected` (with `value = sender`) when any WebSocket client leaves. Since `sender` is stable per device (`tablet_ui`), a single tab refresh would fire `client_disconnected` for `"tablet_ui"` — which would kill every WebRTC connection belonging to that sender, including ones held by other open tabs.

Instead, each `<webrtc-stream>` component sends an explicit `webrtc_disconnect` with its specific `viewerId` when it's removed from the DOM or the page unloads. TD disconnects only that one connection. Connections from other tabs or components on the same page are unaffected. For abrupt disconnects (browser crash), the WebRTC ICE keepalive detects the peer is gone and cleans up naturally.

---

## TouchDesigner network setup

All operators live inside a single **Base COMP** with the `WebRTCVideoOut` extension attached.

### Operators required

| Operator | Name | Purpose |
|---|---|---|
| WebSocket DAT | `websocket2` | Connects to Oversite server; carries signaling |
| WebRTC DAT | `webrtc2` | Manages peer connections |
| Table DAT | `active_streams` | Replicator source; one row per live connection |
| Replicator COMP | `replicator1` | Spawns one VideoStreamOut TOP per viewer |
| Base COMP (template) | `template_viewer` | Master template containing VideoStreamOut TOP |

### WebSocket DAT parameters

- **Network Address:** `[server-ip]` **Port:** `3003`
- **Active path:** `/ws?sender=td_webrtc&channel=default`
- **Active:** On
- **Callbacks DAT:** `ws_callbacks`

### VideoStreamOut TOP (inside template Base COMP)

- **WebRTC DAT:** `op('../../webrtc2')`
- **WebRTC Video Track:** `video_track_1` ← must match the string passed to `addTrack()`
- **WebRTC Connection** (expression): `op('../../active_streams')[me.parent().digits, 0]`

### Replicator COMP

- **Master:** `template_viewer`
- **Replicant Table:** `active_streams`

---

## DAT callback scripts

### `ws_callbacks` Script DAT

```python
def onReceiveText(dat, rowIndex, message):
    ext.WebRTCVideoOut.OnReceiveText(dat, rowIndex, message)

def onConnect(dat):    pass
def onDisconnect(dat): pass
```

### `webrtc_callbacks` Script DAT

```python
def onOffer(webrtcDAT, connectionId, localSdp):
    ext.WebRTCVideoOut.OnOffer(webrtcDAT, connectionId, localSdp)

def onIceCandidate(webrtcDAT, connectionId, candidate, lineIndex, sdpMid):
    ext.WebRTCVideoOut.OnIceCandidate(webrtcDAT, connectionId, candidate, lineIndex, sdpMid)

def onAnswer(webrtcDAT, connectionId, localSdp):                pass
def onNegotiationNeeded(webrtcDAT, connectionId):               pass
def onIceCandidateError(webrtcDAT, connectionId, errorText):    pass
def onTrack(webrtcDAT, connectionId, trackId, type):            pass
def onRemoveTrack(webrtcDAT, connectionId, trackId, type):      pass
def onConnectionStateChange(webrtcDAT, connectionId, newState): pass
def onSignalingStateChange(webrtcDAT, connectionId, newState):  pass
def onIceConnectionStateChange(webrtcDAT, connectionId, newState):  pass
def onIceGatheringStateChange(webrtcDAT, connectionId, newState):   pass
```

> `onConnectionStateChange` is the hook to use for managing the `active_streams` table — add a row when `newState == 'connected'`, remove it when `newState in ('disconnected', 'failed', 'closed')`.

---

## Browser web component usage

The `sender` attribute on `<app-store-init>` is the **device identity** — keep it stable and meaningful (e.g. `tablet_ui`). It does not need to be unique per tab. The `<webrtc-stream>` component generates its own unique `viewerId` automatically.

```html
<app-store-init sender="tablet_ui" channel="default"></app-store-init>

<webrtc-stream></webrtc-stream>
```

To place multiple streams on one page, give each a distinct `webrtc-id`:

```html
<webrtc-stream webrtc-id="webrtc_viewer_cam1"></webrtc-stream>
<webrtc-stream webrtc-id="webrtc_viewer_cam2"></webrtc-stream>
```

If `webrtc-id` is omitted the component auto-generates one (`webrtc_viewer_<random>`), which is sufficient for single-stream pages.

The component handles the full browser-side signaling flow, ICE candidate buffering, reconnection on failure, aspect ratio detection from the incoming stream, and rendering the video element.

---

## Future development ideas

- Do we need a list of connections, since the WebRTC DAT tracks them in a table?
- How can we support multiple video tracks, depending on the incoming request? (e.g. "video_track_1" for 720p, "video_track_2" for 1080p)
- How can we add audio tracks? (WebRTC supports this but it's outside the scope of the current use case)
- Can we send video *in* to TouchDesigner using the same architecture? (e.g. for a remote webcam feed)
- Can we support running this from a local device to a remote browser over the internet? This would require STUN/TURN servers for NAT traversal, and potentially more complex signaling to handle dynamic IPs and firewall restrictions.

---

## References

- [TouchDesigner WebRTC Remote Panel Web Demo](https://github.com/TouchDesigner/WebRTC-Remote-Panel-Web-Demo)
- [TouchDesigner Signaling API](https://github.com/TouchDesigner/SignalingAPI)
- [TD Signaling API docs](https://docs.derivative.ca/Palette:signalingServer#Signaling_API)
- [TD WebRTC LAN community example](https://github.com/jshea2/TD-WebRTC-LAN)
