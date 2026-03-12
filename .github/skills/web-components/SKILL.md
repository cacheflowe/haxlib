---
name: web-components
description: Guidance for working with web components in this project. Use this when building or styling component-based web UI features.
---


- All frontend components are built as vanilla web components
- If a UI component might be used multiple times on a page, we recommend extending the `AppStoreElement` base class, which provides a simple interface for connecting to the AppStore and reacting to changes in store values.
- CSS in a web component should be scoped to the component itself, and not affect other elements on the page. To achieve this, we recommend using the `:host` selector in your component's CSS to target the component's root element, and/or using the component name as a selector to target the component's root element. For example, if your component is named `my-component`, you can use the following CSS to style the component's root element:

```css  
:host {
  /* styles for the component's root element */
} 
my-component {
  /* styles for the component's root element */
}
```

- Refactor AppStoreElement 
  - Subclasses now use subclassInit() when _store is ready
  - UI elements should use super.render() and allow creation of a single <style> element
- AppStore.checkStoreReady() to wait for _store