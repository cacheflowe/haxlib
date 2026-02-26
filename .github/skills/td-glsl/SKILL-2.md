# TouchDesigner GLSL Reference

Best practices and reference for writing GLSL shaders in TouchDesigner.

## Documentation

- [Write a GLSL TOP](https://docs.derivative.ca/Write_a_GLSL_TOP)
- [GLSL TOP](https://derivative.ca/UserGuide/GLSL_TOP)
- [Write a GLSL Material](https://derivative.ca/UserGuide/Write_a_GLSL_Material)

## Framework Basics

TouchDesigner uses GLSL 4.60 (Vulkan backend). Shaders run once per pixel on a full-screen quad.

### Minimal Pixel Shader

```glsl
layout(location = 0) out vec4 fragColor;
void main()
{
    vec4 color = vec4(1.0, 0.0, 0.0, 1.0);
    fragColor = TDOutputSwizzle(color);
}
```

### Key Rules

- `main()` takes no arguments
- Final color must pass through `TDOutputSwizzle()` for cross-platform correctness
- Do not add a `#version` statement — TD adds it automatically
- Do not declare `uniform sampler2D sTD2DInputs` or `in vec2 vUV` — provided by framework
- If there's a `uTime` uniform in ported code, replace with `iTime`
- Replace `iChannel0` with `sTD2DInputs[0]`
- Replace custom noise with `TDSimplexNoise()` or `TDPerlinNoise()`
- Replace custom random with the built-in `sTDNoiseMap` sampler

## Sampling Inputs

```glsl
// Sample the first 2D input at current pixel
vec4 color = texture(sTD2DInputs[0], vUV.st);

// Second 2D input
vec4 color2 = texture(sTD2DInputs[1], vUV.st);
```

`vUV` is auto-provided in pixel shaders (not in compute shaders or custom vertex shaders). Samplers are arrays grouped by dimensionality:

```glsl
// These are declared for you — do NOT redeclare
uniform sampler2D sTD2DInputs[TD_NUM_2D_INPUTS];
uniform sampler3D sTD3DInputs[TD_NUM_3D_INPUTS];
uniform sampler2DArray sTD2DArrayInputs[TD_NUM_2D_ARRAY_INPUTS];
uniform samplerCube sTDCubeInputs[TD_NUM_CUBE_INPUTS];
```

### Sampling Neighboring Pixels

```glsl
// Helper for offset sampling (declare this yourself)
vec2 input2DOffset(int texIndex, int xOffset, int yOffset)
{
    return vec2(vUV.s + (float(xOffset) * uTD2DInfos[texIndex].res.s),
               vUV.t + (float(yOffset) * uTD2DInfos[texIndex].res.t));
}

// Usage: simple 3x3 blur
vec4 colorSum = vec4(0.0);
for (int y = -1; y <= 1; y++)
    for (int x = -1; x <= 1; x++)
        colorSum += texture(sTD2DInputs[0], input2DOffset(0, x, y));
fragColor = TDOutputSwizzle(colorSum / 9.0);
```

## Built-in Uniforms

### Texture Info

```glsl
struct TDTexInfo {
    vec4 res;    // (1/width, 1/height, width, height)
    vec4 depth;  // (1/depth, depth, depthOffset, undefined)
};

uniform TDTexInfo uTDOutputInfo;                         // Output texture info
uniform TDTexInfo uTD2DInfos[TD_NUM_2D_INPUTS];         // Per-input info
uniform TDTexInfo uTD3DInfos[TD_NUM_3D_INPUTS];
uniform TDTexInfo uTD2DArrayInfos[TD_NUM_2D_ARRAY_INPUTS];
uniform TDTexInfo uTDCubeInfos[TD_NUM_CUBE_INPUTS];
```

### Other Built-in Uniforms

```glsl
uniform int uTDCurrentDepth;  // Current depth slice index (3D/2DArray output)
uniform int uTDPass;          // Current render pass (multi-pass)
```

### Built-in Samplers

```glsl
uniform sampler2D sTDNoiseMap;    // 256x256 8-bit random data (Red only)
uniform sampler1D sTDSineLookup;  // Sine wave 0-1 (Red only)
```

## Built-in Functions

```glsl
// Output swizzle — always wrap final color with this
vec4 TDOutputSwizzle(vec4 c);

// Noise (results between -1 and 1, deterministic for same input)
float TDPerlinNoise(vec2 v);
float TDPerlinNoise(vec3 v);
float TDPerlinNoise(vec4 v);
float TDSimplexNoise(vec2 v);
float TDSimplexNoise(vec3 v);
float TDSimplexNoise(vec4 v);

// Color conversion
vec3 TDHSVToRGB(vec3 c);
vec3 TDRGBToHSV(vec3 c);

// Anti-banding dither
vec4 TDDither(vec4 color);

// Matrix helpers
mat4 TDTranslate(float x, float y, float z);
mat3 TDRotateX(float radians);
mat3 TDRotateY(float radians);
mat3 TDRotateZ(float radians);
mat3 TDRotateOnAxis(float radians, vec3 axis);  // axis must be normalized
mat3 TDScale(float x, float y, float z);
mat3 TDRotateToVector(vec3 forward, vec3 up);    // vectors don't need normalizing
mat3 TDCreateRotMatrix(vec3 from, vec3 to);      // vectors must be normalized
```

## Common Snippets

### Constants

```glsl
#define PI     3.14159265358
#define TWO_PI 6.28318530718
```

### Aspect-Correct Coordinates

```glsl
float width = 1.0 / uTDOutputInfo.res.z;
float height = 1.0 / uTDOutputInfo.res.w;
vec2 aspect = width * uTDOutputInfo.res.wz;  // swizzle height/width
vec2 p = vUV.xy / aspect;
```

### Centered Coordinate System

```glsl
vec2 p = (vUV.st - vec2(0.5)) / aspect;
```

## Custom Uniforms

Declare uniforms in your shader, set values on the GLSL TOP's Vectors pages:

```glsl
uniform vec4 uColor;
uniform float uSpeed;

void main()
{
    fragColor = TDOutputSwizzle(uColor * uSpeed);
}
```

**Important:** After adding custom uniforms, press "Load Uniform Names" on the GLSL TOP to make parameters appear.

## Compute Shaders

Compute shaders don't have `vUV` — calculate coordinates manually. Output uses `TDImageStoreOutput()` instead of `fragColor` (no need for `TDOutputSwizzle`):

```glsl
void TDImageStoreOutput(uint index, ivec3 coord, vec4 color);
vec4 TDImageLoadOutput(uint index, ivec3 coord);

void main()
{
    vec4 color = vec4(1, 0, 0, 1);
    TDImageStoreOutput(0, ivec3(gl_GlobalInvocationID.xy, 0), color);
}
```

## Multiple Color Buffers

Turn up "# of Color Buffers" on the GLSL TOP, then declare multiple outputs:

```glsl
layout(location = 0) out vec4 fragColor;
layout(location = 1) out vec4 otherColor;
layout(location = 2) out vec4 extraInfo;
```

Use a Render Select TOP to access buffers beyond the first.

## Non-Uniform Sampler Access

When the sampler index depends on runtime values (not compile-time constants), wrap with `nonuniformEXT()`:

```glsl
int inputIndex = (vUV.s > 0.5) ? 0 : 1;
vec4 col = texture(sTD2DInputs[nonuniformEXT(inputIndex)], vUV.st);
```

## POP Attribute Buffers

```glsl
attribType TDBuffer_AttribName(uint elementIndex, uint arrayIndex);
attribType TDBuffer_AttribName(uint elementIndex);  // arrayIndex defaults to 0
const uint TDBufferLength_AttribName();
const uint cTDBufferArraySize_AttribName;
```

## Code Style

- Prefix custom uniforms with `u` (e.g., `uColor`, `uSpeed`)
- Expand compact "code golf" into readable multi-line code
- Add comments for complex math
- Group uniforms and constants at the top, helper functions before `main()`

## See Also

- [td-python-patterns.md](td-python-patterns.md) — Python patterns (TOP pixel access via `numpyArray()`)
- [prompt-glsl-cleanup.md](prompt-glsl-cleanup.md) — AI prompt for cleaning up GLSL code
