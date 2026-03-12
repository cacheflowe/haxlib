---
name: picocss-customization
description: Guide for customizing Pico CSS variables and color schemes. Use this when updating theme variables or styling the web UI.
---

# Pico CSS Color Customization

How to customize colors in a site that uses Pico CSS via CSS custom properties (variables).

## Documentation Reference

- **Pico CSS Variables**: https://picocss.com/docs/css-variables
- **Pico SASS Customization**: https://picocss.com/docs/sass

## Key Concepts

- All Pico CSS variables are prefixed with `--pico-` to avoid collisions.
- Override variables on `:root` for global changes, or on specific selectors for local changes.
- Color variables are **scheme-dependent** — they must be defined separately for light and dark modes.
- Style variables (font, spacing, border-radius, etc.) are scheme-independent and go on `:root, :host`.

## Color Scheme Selectors

When overriding color variables, use the correct selector pattern for each scheme. Both light and dark overrides are required for full theme support.

### Light Mode

```css
/* Light color scheme (Default) */
/* Can be forced with data-theme="light" */
[data-theme="light"],
:root:not([data-theme="dark"]),
:host:not([data-theme="dark"]) {
  /* your light color overrides here */
}
```

### Dark Mode

Dark mode requires **two** declarations:

1. An `@media` query for users with OS-level dark mode (auto-detection).
2. A `[data-theme="dark"]` block for forced/manual dark mode.

```css
/* Dark color scheme (Auto) */
/* Automatically enabled if user has dark mode enabled in OS */
@media only screen and (prefers-color-scheme: dark) {
  :root:not([data-theme]),
  :host:not([data-theme]) {
    /* your dark color overrides here */
  }
}

/* Dark color scheme (Forced) */
/* Enabled when manually set with data-theme="dark" */
[data-theme="dark"] {
  /* same dark color overrides here (duplicated) */
}
```

## Primary Color Variables

The primary color is the most common customization. Override all related variables together for consistency:

| Variable | Purpose |
|----------|---------|
| `--pico-primary` | Main text/link color for primary elements |
| `--pico-primary-background` | Background of primary buttons, switches, progress bars |
| `--pico-primary-border` | Border of primary buttons (usually matches background) |
| `--pico-primary-underline` | Underline color on primary links |
| `--pico-primary-hover` | Text/link color on hover |
| `--pico-primary-hover-background` | Button background on hover |
| `--pico-primary-hover-border` | Button border on hover |
| `--pico-primary-focus` | Focus ring color (use semi-transparent) |
| `--pico-primary-inverse` | Text color on primary background (usually `#fff`) |
| `--pico-text-selection-color` | Text highlight color (use semi-transparent) |

### Example: Orange Primary Color

```css
/* Light mode */
[data-theme=light],
:root:not([data-theme=dark]),
:host:not([data-theme=dark]) {
  --pico-text-selection-color: rgba(244, 93, 44, 0.25);
  --pico-primary: #bd3c13;
  --pico-primary-background: #d24317;
  --pico-primary-underline: rgba(189, 60, 19, 0.5);
  --pico-primary-hover: #942d0d;
  --pico-primary-hover-background: #bd3c13;
  --pico-primary-focus: rgba(244, 93, 44, 0.5);
  --pico-primary-inverse: #fff;
}

/* Dark mode (Auto) */
@media only screen and (prefers-color-scheme: dark) {
  :root:not([data-theme]),
  :host:not([data-theme]) {
    --pico-text-selection-color: rgba(245, 107, 61, 0.1875);
    --pico-primary: #f56b3d;
    --pico-primary-background: #d24317;
    --pico-primary-underline: rgba(245, 107, 61, 0.5);
    --pico-primary-hover: #f8a283;
    --pico-primary-hover-background: #e74b1a;
    --pico-primary-focus: rgba(245, 107, 61, 0.375);
    --pico-primary-inverse: #fff;
  }
}

/* Dark mode (Forced) */
[data-theme=dark] {
  --pico-text-selection-color: rgba(245, 107, 61, 0.1875);
  --pico-primary: #f56b3d;
  --pico-primary-background: #d24317;
  --pico-primary-underline: rgba(245, 107, 61, 0.5);
  --pico-primary-hover: #f8a283;
  --pico-primary-hover-background: #e74b1a;
  --pico-primary-focus: rgba(245, 107, 61, 0.375);
  --pico-primary-inverse: #fff;
}
```

## Secondary & Contrast Color Variables

The same pattern applies to secondary and contrast colors:

| Color Group | Prefix | Purpose |
|-------------|--------|---------|
| **Secondary** | `--pico-secondary-*` | Secondary buttons, links with `.secondary` class |
| **Contrast** | `--pico-contrast-*` | High-contrast elements, links with `.contrast` class |

Each group has the same set of sub-variables as primary: base, `-background`, `-border`, `-underline`, `-hover`, `-hover-background`, `-hover-border`, `-focus`, `-inverse`.

## Surface & Background Colors

| Variable | Purpose |
|----------|---------|
| `--pico-background-color` | Page background |
| `--pico-color` | Default text color |
| `--pico-muted-color` | Subdued text (placeholders, captions) |
| `--pico-muted-border-color` | Light borders, separators |
| `--pico-card-background-color` | Card backgrounds |
| `--pico-card-border-color` | Card borders |
| `--pico-card-sectioning-background-color` | Card header/footer backgrounds |
| `--pico-code-background-color` | Code block backgrounds |
| `--pico-code-color` | Code text color |
| `--pico-dropdown-background-color` | Dropdown menu backgrounds |
| `--pico-dropdown-border-color` | Dropdown borders |
| `--pico-dropdown-hover-background-color` | Dropdown item hover |
| `--pico-modal-overlay-background-color` | Modal backdrop overlay |

## Heading Colors

Each heading level has its own color variable, creating a subtle hierarchy:

| Variable | Default (Light) | Default (Dark) |
|----------|-----------------|----------------|
| `--pico-h1-color` | `#2d3138` | `#f0f1f3` |
| `--pico-h2-color` | `#373c44` | `#e0e3e7` |
| `--pico-h3-color` | `#424751` | `#c2c7d0` |
| `--pico-h4-color` | `#4d535e` | `#b3b9c5` |
| `--pico-h5-color` | `#5c6370` | `#a4acba` |
| `--pico-h6-color` | `#646b79` | `#8891a4` |

## Form Element Colors

| Variable | Purpose |
|----------|---------|
| `--pico-form-element-background-color` | Input/select/textarea background |
| `--pico-form-element-border-color` | Input border |
| `--pico-form-element-color` | Input text color |
| `--pico-form-element-placeholder-color` | Placeholder text |
| `--pico-form-element-active-background-color` | Focused input background |
| `--pico-form-element-active-border-color` | Focused input border |
| `--pico-form-element-focus-color` | Focus ring |
| `--pico-form-element-valid-border-color` | Valid input border |
| `--pico-form-element-invalid-border-color` | Invalid input border |
| `--pico-switch-background-color` | Toggle switch track (off) |
| `--pico-switch-checked-background-color` | Toggle switch track (on) |
| `--pico-range-thumb-color` | Range slider thumb |

## Miscellaneous Colors

| Variable | Purpose |
|----------|---------|
| `--pico-mark-background-color` | `<mark>` highlight background |
| `--pico-mark-color` | `<mark>` text color |
| `--pico-ins-color` | `<ins>` inserted text color |
| `--pico-del-color` | `<del>` deleted text color |
| `--pico-blockquote-border-color` | Blockquote left border |
| `--pico-table-border-color` | Table borders |
| `--pico-table-row-stripped-background-color` | Striped table row background |
| `--pico-progress-background-color` | Progress bar track |
| `--pico-progress-color` | Progress bar fill |
| `--pico-tooltip-background-color` | Tooltip background |
| `--pico-tooltip-color` | Tooltip text |
| `--pico-box-shadow` | Default box shadow (cards, dropdowns) |
| `--pico-loading-spinner-opacity` | Loading spinner opacity |

## Style Variables (Scheme-Independent)

These go on `:root, :host` without color scheme selectors:

```css
:root, :host {
  --pico-font-family: system-ui, sans-serif;
  --pico-font-size: 100%;          /* responsive, scales up at breakpoints */
  --pico-line-height: 1.5;
  --pico-font-weight: 400;
  --pico-border-radius: 0.25rem;
  --pico-border-width: 0.0625rem;
  --pico-outline-width: 0.125rem;
  --pico-transition: 0.2s ease-in-out;
  --pico-spacing: 1rem;            /* base for padding/margin/gaps */
  --pico-block-spacing-vertical: var(--pico-spacing);
  --pico-block-spacing-horizontal: var(--pico-spacing);
  --pico-form-element-spacing-vertical: 0.75rem;
  --pico-form-element-spacing-horizontal: 1rem;
}
```

## Best Practices

- **Always override both light and dark** color schemes to avoid mismatched themes.
- **Dark mode values must appear twice**: once in `@media (prefers-color-scheme: dark)` and once in `[data-theme=dark]`.
- Use **semi-transparent rgba values** for focus, selection, and underline colors.
- In dark mode, make primary colors **lighter** than in light mode for adequate contrast.
- The `-border` variables typically reference `-background` via `var()` — only override them if you want distinct borders.
- To customize the prefix or do deeper modifications, recompile with SASS: https://picocss.com/docs/sass
