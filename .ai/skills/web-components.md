---
name: web-components
description: Guidance for working with web components in this project. Use this when building or styling component-based web UI features.
---

## Quick Rules

- **Vanilla JS only** — no TypeScript, no frameworks (React/Vue/Svelte)
- **No Shadow DOM** unless the component already uses it
- All components are ES6 classes extending `HTMLElement` or `AppStoreElement`
- Use `/*html*/` and `/*css*/` tagged template comments for editor syntax highlighting
- Every component self-registers at the bottom of its file and exports itself as default
- Use `.js` extension for frontend component files
- Kebab-case filenames: `my-component.js`

## Two Component Types

### 1. Store-Connected Components (extend `AppStoreElement`)

For components that read/write AppStore state. Import from `src/components/ui/app-store-element.js`.

**Lifecycle:** `connectedCallback()` → `initComponent()` → `render()` → (store ready) → `subclassInit()` → `storeUpdated()` on changes

**Key overrides:**
- `subclassInit()` — runs once when `_store` is ready; set up event listeners, cache DOM refs
- `setStoreValue(value)` — called when the store key changes; update DOM to reflect new value
- `css()` — return component-scoped CSS string
- `html()` — return HTML template string
- `render()` — calls `this.el.innerHTML = this.html()`, `this.injectHeadStyles()`, and `this.handleObservedAttributes()`. Override only if you need custom render logic

**Attributes:** `key` (or `store-key`), `value` (or `store-value`), `flash-on-update`, `disabled`

**Minimal example:**
```javascript
import AppStoreElement from "./app-store-element.js";

class MyDisplay extends AppStoreElement {
  setStoreValue(value) {
    this.el.querySelector(".value").textContent = value;
  }

  css() {
    return /*css*/ `
      my-display {
        .value { font-weight: bold; }
      }
    `;
  }

  html() {
    return /*html*/ `
      <div class="value">${this.valueFromStore ?? ""}</div>
    `;
  }

  static register() {
    customElements.define("my-display", MyDisplay);
  }
}

MyDisplay.register();
export default MyDisplay;
```

### 2. Standalone Components (extend `HTMLElement`)

For components with no AppStore dependency. Most only need `connectedCallback()`, `render()`, and `register()`.

## Full Robust Example (HTMLElement)

This example shows every vanilla web component feature we use. Most components will only need a subset of this. Copy what you need; delete the rest.

```javascript
class CustomButton extends HTMLElement {
  static NODE_NAME = "custom-button";
  static GLOBAL_CSS = true; // when true, styles go in <head> once; when false, styles inline per instance

  /////////////////////////////////////////////////////////
  // Lifecycle
  /////////////////////////////////////////////////////////

  connectedCallback() {
    this.initialHTML = this.innerHTML; // capture slot content before render overwrites it
    // this.shadow = this.attachShadow({ mode: "open" }); // uncomment only if Shadow DOM is needed
    this.el = this.shadow ? this.shadow : this; // universal render target
    this.init();
    this.render();
  }

  disconnectedCallback() {
    // clean up listeners, observers, timers here
    this.resizeObserver?.disconnect();
  }

  adoptedCallback() {
    // called when element is moved to a new document (rare)
  }

  /////////////////////////////////////////////////////////
  // Setup
  /////////////////////////////////////////////////////////

  init() {
    this.querySelector("button").addEventListener("click", (e) => {
      let randomColor = Math.floor(Math.random() * 16777215).toString(16);
      document.documentElement.style.backgroundColor = `#${randomColor}`;
    });
  }

  /////////////////////////////////////////////////////////
  // Attribute Observation
  /////////////////////////////////////////////////////////

  static observedAttributes = ["color", "debug"];

  attributeChangedCallback(name, oldValue, newValue) {
    // react to attribute changes on this element
  }

  /////////////////////////////////////////////////////////
  // CSS & Rendering
  /////////////////////////////////////////////////////////

  static css = /*css*/ `
    :host {
      display: block;
      container-type: inline-size;
    }

    @container (min-width: 400px) {
      button { color: #ffffff; }
    }

    ${CustomButton.NODE_NAME} button {
      border-radius: 4px;
      padding: 1rem 2rem;
      cursor: pointer;
    }
  `;

  static addGlobalStyles() {
    if (!CustomButton.GLOBAL_CSS) return;
    let styleId = CustomButton.NODE_NAME + "-style";
    if (document.getElementById(styleId)) return;
    const style = document.createElement("style");
    style.id = styleId;
    style.textContent = CustomButton.css;
    document.head.appendChild(style);
  }

  html() {
    return /*html*/ `
      <button>Web Component Button</button>
    `;
  }

  render() {
    if (!CustomButton.GLOBAL_CSS) {
      this.el.innerHTML = /*html*/ `
        ${this.html()}
        <style>${CustomButton.css}</style>
      `;
    } else {
      this.el.innerHTML = /*html*/ this.html();
    }
  }

  /////////////////////////////////////////////////////////
  // Extras (optional)
  /////////////////////////////////////////////////////////

  addResizeListener() {
    this.resizeObserver?.disconnect();
    this.resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        this.resized();
      }
    });
    this.resizeObserver.observe(this.container);
  }

  resized() {
    const bb = this.container.getBoundingClientRect();
    console.log(`Component resized: ${bb.width}x${bb.height}`);
  }

  /////////////////////////////////////////////////////////
  // Registration
  /////////////////////////////////////////////////////////

  static register() {
    if ("customElements" in window) {
      window.customElements.define(CustomButton.NODE_NAME, CustomButton);
      CustomButton.addGlobalStyles();
    }
  }
}

CustomButton.register();
export default CustomButton;
```

## CSS Strategy

| Scenario | Approach |
|---|---|
| **AppStoreElement subclass** | Override `css()` method → `injectHeadStyles()` adds one `<style>` to `<head>` per tag name |
| **HTMLElement, shared styles** | `static GLOBAL_CSS = true` → `addGlobalStyles()` injects once to `<head>` |
| **HTMLElement, scoped styles** | `static GLOBAL_CSS = false` → inline `<style>` inside `render()` |
| **Shadow DOM** (rare) | Inline `<style>` inside shadow root |

**CSS selectors:** Use the component tag name as the top-level selector (e.g., `my-component { ... }`). Use `:host` when targeting the component root in Shadow DOM or for `display`/`container-type` declarations. Native CSS nesting is preferred.

**PicoCSS:** The project uses PicoCSS for base/semantic styling. Don't fight it — let it handle typography, forms, and layout defaults. Only add component CSS for component-specific styling.

## Patterns & Conventions

- **`this.el`** — always render into `this.el`, which is `this` (light DOM) or `this.shadow` (shadow DOM)
- **`this.initialHTML`** — capture `this.innerHTML` before rendering to preserve any content placed inside the tag in HTML
- **`static NODE_NAME`** — store the tag name as a static for use in `register()` and CSS selectors
- **Section comments** — use the project-standard section dividers:
  ```javascript
  /////////////////////////////////////////////////////////
  // Section Name
  /////////////////////////////////////////////////////////
  ```
- **Registration** — every component file ends with:
  ```javascript
  MyComponent.register();
  export default MyComponent;
  ```
- **Component registration file** — add new components to `src/components/_register-components.js` as a bare import (the import triggers the self-executing `register()` call)
- **Cleanup** — always disconnect observers, remove listeners, and clear timers in `disconnectedCallback()` to prevent memory leaks