import AppStore from "oversite/src/app-store/app-store-.mjs";

/**
 * <webrtc-stream> — Receives a WebRTC video stream via WebSocket signaling.
 *
 * Piggybacks on the existing AppStore WebSocket channel for offer/answer/ICE signaling.
 * Uses the official TouchDesigner Signaling API message format.
 * No STUN/TURN required on a local network.
 *
 * References:
 *   https://github.com/TouchDesigner/WebRTC-Remote-Panel-Web-Demo
 *   https://docs.derivative.ca/Palette:signalingServer#Signaling_API
 *   https://github.com/TouchDesigner/SignalingAPI
 *   https://derivative.ca/UserGuide/WebRTC
 */

const METADATA = {
  apiVersion: "1.0.1",
  compVersion: "1.0.0",
  compOrigin: "oversite/webrtc-stream",
  projectName: "oversite",
};

class WebRTCStream extends HTMLElement {
  static NODE_NAME = "webrtc-stream";
  static GLOBAL_CSS = true;

  /////////////////////////////////////////////////////////
  // Lifecycle
  /////////////////////////////////////////////////////////

  connectedCallback() {
    this.el = this;
    AppStore.checkStoreReady(this);
  }

  disconnectedCallback() {
    clearTimeout(this._requestTimer);
    window.removeEventListener("beforeunload", this._onBeforeUnload);
    _store.removeListener(this, "appstore_connected");
    _store.removeListener(this, "custom_json");
    this._sendDisconnect();
    this.closeConnection();
  }

  _sendDisconnect() {
    if (this._viewerId) _store.set("webrtc_disconnect", this._viewerId, /*broadcast*/true, /*receiverId*/null, /*sendOnly*/true);
  }

  storeIsReady() {
    this.render();
    this.video = this.querySelector("video");
    this.video.addEventListener("loadedmetadata", () => this._onVideoMetadata());
    this._onBeforeUnload = () => this._sendDisconnect();
    window.addEventListener("beforeunload", this._onBeforeUnload);
    // Use the webrtc-id attribute if set; otherwise auto-generate a unique viewer ID
    // and persist it as an attribute so it's visible in the DOM and stable across reconnects
    if (!this.getAttribute("webrtc-id")) {
      this.setAttribute("webrtc-id", "webrtc_viewer_" + Math.random().toString(36).slice(2, 7));
    }
    this._viewerId = this.getAttribute("webrtc-id");
    this.initPeerConnection();
    _store.addListener(this, "custom_json");
    // SolidSocket connects asynchronously — wait for the WebSocket to be open before sending
    if (_store.isConnected()) {
      this._requestWebRTC();
    } else {
      _store.addListener(this, "appstore_connected");
    }
  }

  appstore_connected() {
    _store.removeListener(this, "appstore_connected");
    this._requestWebRTC();
  }

  _requestWebRTC() {
    // Debounce: collapse rapid retriggers (failed + reconnect arriving together)
    clearTimeout(this._requestTimer);
    this._requestTimer = setTimeout(() => {
      // sender = page's WS identity (for routing); value = this component's viewer ID
      // (TD echoes viewerId back in the Offer so the component can verify it's the right one)
      _store.set("webrtc_request", this._viewerId, /*broadcast*/true, /*receiverId*/null, /*sendOnly*/true);
    }, 300);
  }

  _onVideoMetadata() {
    const { videoWidth, videoHeight } = this.video;
    if (videoWidth && videoHeight) {
      this.style.aspectRatio = `${videoWidth} / ${videoHeight}`;
    }
  }

  /////////////////////////////////////////////////////////
  // WebRTC
  /////////////////////////////////////////////////////////

  initPeerConnection() {
    this.target = null; // TD's address — learned from incoming Offer's sender field
    this.iceBuffer = []; // holds candidates that arrive before remote description is set
    this.pc = new RTCPeerConnection(); // no STUN/TURN needed for LAN
    this.pc.ontrack = ({ track, streams }) => {
      if (streams[0]) {
        if (this.video.srcObject !== streams[0]) this.video.srcObject = streams[0];
      } else {
        // TD WebRTC DAT may not bundle the track in a stream — build one manually
        if (!this.video.srcObject) this.video.srcObject = new MediaStream();
        this.video.srcObject.addTrack(track);
      }
    };
    this.pc.onicecandidate = ({ candidate }) => {
      if (candidate) {
        this.sendSignal({
          signalingType: "Ice",
          target: this.target,
          content: {
            sdpCandidate: candidate.candidate,
            sdpMLineIndex: candidate.sdpMLineIndex,
            sdpMid: candidate.sdpMid,
          },
        });
      }
    };
    this.pc.onconnectionstatechange = () => {
      const state = this.pc.connectionState;
      this.dataset.state = state;
      const status = this.querySelector("#status");
      if (status) status.textContent = state;
      console.log("WebRTCStream:", state);
      // auto-retry when ICE fails — ask TD for a fresh offer
      if (state === "failed") this._requestWebRTC();
    };
  }

  async custom_json(data) {
    if (!this.pc || !data.signalingType) return;
    // ignore signals not addressed to this component instance
    if (data.viewerId && data.viewerId !== this._viewerId) return;
    console.log("WebRTCStream: custom_json", data.signalingType, "pc:", this.pc?.signalingState ?? "none");
    switch (data.signalingType) {
      case "Offer":
        await this.handleOffer(data);
        break;
      case "Ice":
        // ignore our own ICE echoes reflected by the server
        if (data.sender !== _store.senderId) {
          console.log("WebRTCStream: ICE from", data.sender, data.content?.sdpCandidate?.slice(0, 60));
          await this.handleIce(data);
        } else {
          console.log("WebRTCStream: skipping own ICE echo");
        }
        break;
      // "Answer" is ignored — browser is always the answerer, never the offerer.
    }
  }

  async handleOffer(data) {
    try {
      // learn TD's address for targeting our outgoing messages
      this.target = data.sender ?? null;
      // restart the peer connection if signaling is stuck or the previous attempt failed
      if (this.pc.signalingState !== "stable" || this.pc.connectionState === "failed") {
        this.closeConnection();
        this.initPeerConnection();
        this.target = data.sender ?? null;
      }
      const pc = this.pc; // capture ref — avoids stale-PC issues if a concurrent offer restarts it
      console.log("WebRTCStream: setting remote description (offer)");
      await pc.setRemoteDescription({ type: "offer", sdp: data.content.sdp });
      // flush any ICE candidates that arrived before the remote description was ready
      const flushed = this.iceBuffer.splice(0);
      if (flushed.length) console.log("WebRTCStream: flushing", flushed.length, "buffered ICE candidates");
      for (const c of flushed) await this._addIceCandidate(pc, c);
      const answer = await pc.createAnswer();
      if (pc !== this.pc) return; // aborted by a newer offer
      await pc.setLocalDescription(answer);
      console.log("WebRTCStream: sent answer, ICE gathering state:", pc.iceGatheringState);
      this.sendSignal({
        signalingType: "Answer",
        target: this.target,
        content: { sdp: pc.localDescription.sdp },
      });
    } catch (e) {
      console.warn("WebRTCStream: handleOffer failed", e);
    }
  }

  async handleIce({ content }) {
    if (!content.sdpCandidate) return;
    if (!this.pc.remoteDescription) {
      this.iceBuffer.push(content); // remote desc not set yet — buffer for later
      return;
    }
    await this._addIceCandidate(this.pc, content);
  }

  async _addIceCandidate(pc, { sdpCandidate, sdpMLineIndex, sdpMid }) {
    try {
      await pc.addIceCandidate(new RTCIceCandidate({ candidate: sdpCandidate, sdpMLineIndex, sdpMid }));
    } catch (e) {
      console.warn("WebRTCStream: failed to add ICE candidate", e);
    }
  }

  sendSignal(msg) {
    _store.broadcastCustomJson({ metadata: METADATA, sender: _store.senderId, viewerId: this._viewerId, ...msg });
  }

  reconnect() {
    this.closeConnection();
    if (this.video) this.video.srcObject = null;
    this.initPeerConnection();
    this._requestWebRTC();
  }

  closeConnection() {
    if (this.pc) {
      this.pc.close();
      this.pc = null;
    }
  }

  /////////////////////////////////////////////////////////
  // CSS & Rendering
  /////////////////////////////////////////////////////////

  static css = /*css*/ `
    webrtc-stream {
      display: block;
      position: relative;
    }
    webrtc-stream video {
      width: 100%;
      height: 100%;
      object-fit: contain;
      transform: scaleX(-1);
    }
    webrtc-stream #reconnect {
      position: absolute;
      bottom: 1rem;
      right: 1rem;
      width: 2rem;
      height: 2rem;
      padding: 0;
      background: rgba(0, 0, 0, 0.5);
      color: #fff;
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 50%;
      cursor: pointer;
      font-size: 1rem;
      opacity: 0.3;
      transition: opacity 0.2s;
    }
    webrtc-stream #reconnect:hover { opacity: 1; }
    webrtc-stream #status {
      position: absolute;
      top: 1rem;
      left: 1rem;
      font-size: 0.75rem;
      font-family: monospace;
      padding: 0.25rem 0.5rem;
      border-radius: 4px;
      background: rgba(0, 0, 0, 0.6);
      color: #888;
      pointer-events: none;
      user-select: none;
    }
    webrtc-stream[data-state="connecting"] #status { color: #fa0; }
    webrtc-stream[data-state="connected"] #status { color: #0f0; }
    webrtc-stream[data-state="disconnected"] #status,
    webrtc-stream[data-state="failed"] #status { color: #f44; }
  `;

  static addGlobalStyles() {
    if (!WebRTCStream.GLOBAL_CSS) return;
    const styleId = WebRTCStream.NODE_NAME + "-style";
    if (document.getElementById(styleId)) return;
    const style = document.createElement("style");
    style.id = styleId;
    style.textContent = WebRTCStream.css;
    document.head.appendChild(style);
  }

  html() {
    return /*html*/ `
      <video autoplay playsinline muted></video>
      <button id="reconnect" title="Reconnect">↺</button>
      <span id="status">waiting for stream…</span>
    `;
  }

  render() {
    this.el.innerHTML = this.html();
    this.querySelector("#reconnect").addEventListener("click", () => this.reconnect());
  }

  /////////////////////////////////////////////////////////
  // Registration
  /////////////////////////////////////////////////////////

  static register() {
    if ("customElements" in window) {
      customElements.define(WebRTCStream.NODE_NAME, WebRTCStream);
      WebRTCStream.addGlobalStyles();
    }
  }
}

WebRTCStream.register();
export default WebRTCStream;
