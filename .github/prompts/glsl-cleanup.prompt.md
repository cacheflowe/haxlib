# GLSL Code Cleanup

Clean up and polish the selected GLSL code following TouchDesigner GLSL conventions.

## Reference

Use the guidelines defined in [SKILL.md](../skills/td-glsl/SKILL.md) for all conventions.

## Cleanup Tasks

### 1. Framework Adaptation
- **Uniforms**: Replace `uTime` with `iTime`. Remove declarations for `sTD2DInputs` or `vUV` (provided by framework).
- **Textures**: Use `sTD2DInputs[0]` instead of `iChannel0`.
- **Noise/Random**: Replace custom noise functions with `TDSimplexNoise(vec2 v)` and random lookups with `sampler2D sTDNoiseMap`.
- **Output**: Ensure `main()` takes no arguments and sets `fragColor = TDOutputSwizzle(vec4(...))`.

### 2. Code Style & Readability
- **De-obfuscate**: Expand ultra-compact "code golf" one-liners into readable multi-line code with meaningful variable names.
- **Comments**: Add comments to explain complex math, algorithms, or logic flow.
- **Formatting**: Use consistent indentation and spacing.
- **Uniforms**: Use meaningful variable names, prefixed with `u`.

### 3. Best Practices
- **Resolution**: Use `uTDOutputInfo.res.z` (width) and `uTDOutputInfo.res.w` (height) for resolution.
- **Aspect Ratio**: Calculate aspect ratio using `uTDOutputInfo.res.wz` (height/width) or similar to ensure correct rendering.
- **Constants**: Define constants like `PI` and `TWO_PI` if used.

### 4. Structure
- Group uniforms and constants at the top.
- Keep helper functions separate from `main()`.
```

## Output

Return the cleaned code with all improvements applied. Preserve the original logic and functionality.
