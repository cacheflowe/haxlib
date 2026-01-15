# TouchDesigner GLSL Coding Skill

This skill defines best practices for writing GLSL code within TouchDesigner projects.

## Documentation Reference

- **TouchDesigner GLSL TOP Reference**: https://derivative.ca/UserGuide/GLSL_TOP
- **TouchDesigner GLSL Reference**: https://derivative.ca/UserGuide/Write_a_GLSL_TOP
- **TouchDesigner GLSL MAT Reference**: https://derivative.ca/UserGuide/Write_a_GLSL_Material
- **TouchDesigner Shader Reference**: https://derivative.ca/UserGuide/Shader

## Best Practices

### Framework Specifics

- There are specific framework-provided uniforms like `vUV`.
- The `main()` function has no argument.
- The final pixel color in a fragment shader is set with `fragColor = TDOutputSwizzle(vec4())`.
- Input textures are sampled by referencing `sTD2DInputs[0]` instead of `iChannel0`.
- If there's a Noise function or a noise texture lookup in the original code, replace it with TouchDesigner's built-in noise function: `TDSimplexNoise(vec2 v)`.
- If there's a Random function or a random texture lookup in the original code, replace it with TouchDesigner's built-in random texture: `sampler2D sTDNoiseMap`.
- If there's a `uTime` uniform, please replace with `iTime`.
- Don't specify `uniform sampler2D sTD2DInputs` or `in vec2 vUV` as they are provided by the TouchDesigner framework.

### Code Style & Readability

- **Clean and Readable**: Avoid ultra-compact "code golf" style GLSL. Expand complex one-liners into multiple lines with meaningful variable names.
- **Comments**: Add comments to explain the logic, especially for complex math or algorithms.
- **Formatting**: Use consistent indentation and spacing to make the code visually appealing and easy to scan.
- **Uniforms**: Use meaningful variable names, prefixed with `u`.

### Built-in Uniforms & Functions

From: https://docs.derivative.ca/Write_a_GLSL_TOP

```glsl
// Helpers
uniform sampler2D sTDNoiseMap;  // A 256x256 8-bit Red-only channel texture that has random data.
uniform sampler1D sTDSineLookup; // A Red-only texture that goes from 0 to 1 in a sine shape.

// Noise functions
float TDPerlinNoise(vec2 v);
float TDPerlinNoise(vec3 v);
float TDPerlinNoise(vec4 v);
float TDSimplexNoise(vec2 v);
float TDSimplexNoise(vec3 v);
float TDSimplexNoise(vec4 v);

// Information about the textures
TDTexInfo uTDOutputInfo; // The current texture context
TDTexInfo uTD2DInfos[]; // only exists if inputs are connected 

// Converts between RGB and HSV color space
vec3 TDHSVToRGB(vec3 c);
vec3 TDRGBToHSV(vec3 c);

// Applies a small random noise to the color to help avoid banding in some cases.
vec4 TDDither(vec4 color);
```

### Common Snippets

**Constants**
```glsl
#define PI     3.14159265358
#define TWO_PI 6.28318530718
```

**Correct Aspect Ratio**
```glsl
float width = 1./uTDOutputInfo.res.z;
float height = 1./uTDOutputInfo.res.w;
vec2 aspect = width * uTDOutputInfo.res.wz; // swizzle height/width
vec2 p = vUV.xy / aspect;
```

**Center Coordinate System**
```glsl
vec2 p = (vUV.st - vec2(0.5)) / aspect;
```

