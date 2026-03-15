import "oversite/shared/css/pico.css";
import "oversite/shared/css/styles.css";

import "oversite/src/components/_register-components.js";
import MobileUtil from "oversite/src/util/mobile-util.mjs";
import ErrorUtil from "oversite/src/util/error-util.mjs";

import "../css/pico.css";
import "../css/client.css";

// register web components
// import ClientUI from "./client-ui.js";
import WebRTCStream from "./webrtc-stream/webrtc-stream.js";

class CustomApp extends HTMLElement {
  connectedCallback() {
    this.init();
    // _store.addListener(this);
  }

  storeUpdated(key, value) {
    // console.log(key, value);
  }

  init() {
    ErrorUtil.initErrorCatching();
    MobileUtil.enablePseudoStyles();
  }
}

customElements.define("custom-app", CustomApp);
