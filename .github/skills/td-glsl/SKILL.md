---
name: td-glsl
description: TouchDesigner GLSL conventions and best practices. Use this when writing or adapting shaders for GLSL TOPs or materials.
---

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

See the official guide to writing a GLSL TOP below:

## Overview

The official GLSL documentation can be found at [https://www.khronos.org/opengl/wiki/Core_Language_(GLSL) this address.]

TouchDesigner's main supported version of GLSL is 4.60. Support for versions of GLSL 3.30 and earlier have been removed due to the switch to Vulkan. A shader written for 3.30 should work fine when targeting newer GLSL though.

A shader written for the [[GLSL TOP]] is generally a image based operation. It does essentially no geometry based work. For users who are familiar with writing 3D GLSL shaders, a GLSL TOP is simply a shader applied to a single quad that is drawn to cover up the entire viewport (also known as a full-screen-aligned quad). 
To simplify the subject, this guide will avoid the extra complexities involved in 3D rendering, and present the topic of writing a GLSL shader in a 2D world only, dealing only with pixels.

The shader code in a GLSL TOP is run once for every pixel that is getting output. It's the job of the shader writer to:

* Sample the pixel(s) of the inputs, if any.
* Do whatever math is needed to create the pixel color.
* Output the pixel color.

## Concepts

### Output Swizzle

To ensure cross-platform support between Windows and macOS, any color written to a texture should be first passed through <syntaxhighlight lang=glsl inline>vec4 TDOutputSwizzle(vec4)```. This function will ensure the correct channels go in the correct output channels depending on the destination texture format. For example alpha-only textures do not actually exist, and are stored as red-only textures. When they are sampled a swizzle is automatically applied to they output (0, 0, 0, R). <syntaxhighlight lang=glsl inline>vec4 TDOutputSwizzle()``` will place the alpha value into the output red channel in that case. When this texture is used else where the value will correctly appear in the 'alpha' channel, using the previously mentioned swizzle.

### Outputting Color
#### Pixel Shader
Usually you will only need a pixel shader to create a functioning GLSL TOP.

A simple shader to start with is one that just sets every pixel to red.
```glsl
layout(location = 0) out vec4 fragColor;
void main()
{
   vec4 color = vec4(1.0, 0.0, 0.0, 1.0);
   fragColor = TDOutputSwizzle(color);
}
```
Simply place this code into a [[DAT]] and set the GLSL TOPs '''Pixel Shader''' parameter to this DAT.

Notice that <code>fragColor</code> is defined by the shader writer as the location where the color is output. This is different from GLSL 1.20 where you used the built in variable <code>gl_FragColor</code>.
#### Compute Shader
For compute shaders the output textures will be defined for you, do not define it in your shader code.

You should write and read from the textures using these functions. The uvec3 versions are there for convivence, but do the same as the ivec3 versions. If the dimension of the output texture doesn't require 3 coordinates, then the extra coordinate is ignored. This is different than the workflow before 2025.30000 series of builds, which used <code>sTDComputeOutputs</code>. This has changed because writing and reading from sRGB encoded textures requires special handling with <code>imageStore()/imageLoad()</code>, so this is handled automatically for you via these functions.
You also do ***not*** need to apply <code>TDOutputSwizzle()</code> to the color before using these functions, it will apply it automatically for you internally.
```glsl
void TDImageStoreOutput(uint index, ivec3 coord, vec4 color);
void TDImageStoreOutput(uint index, uvec3 coord, vec4 color);
vec4 TDImageLoadOutput(uint index, ivec3 coord);
vec4 TDImageLoadOutput(uint index, uvec3 coord);
```

To write to the output, use the GLSL function <code>TDImageStoreOutput()</code>
```glsl
void main()
{
   vec4 color = vec4(1, 0, 0, 1);
   TDImageStoreOutput(0, ivec3(gl_GlobalInvocationID.xy, 0), color);
}
```
### Sampling Inputs

The next thing you will likely want to do is sample the pixels of the input TOP(s). The following line will sample an input TOP using the texture() function:

   vec4 inputColor = texture(sTD2DInputs[0], vUV.st);

#### Pixel Shaders
By default in a pixel shader the input variable <code>vUV</code> is declared/set for you and will contain the texture coordinate of the pixel. This variable is only given if you don't supply a vertex shader. If you supply your own vertex shader than it is up to you to pass the texture coordinate through to the pixel shader. The values will smoothly interpolate across the entire 2D image. so when your drawing the middle pixel the value of <code>vUV.st</code> will be (0.5, 0.5). Input sampler variables are declared for you as arrays. Samplers are split based on their dimensions (2D, 3D, 2DArray, Cube). The sampler that refers to the TOP containing the first 2D texture <code>sTD2DInputs[0]</code>. Similarly, the 2nd 2D input would be called <code>sTD2DInputs[1]</code> and so on for any number of 2D inputs (the GLSL Multi TOP has unlimited inputs, however your video card has a limited number of textures that can be used in a shader).  

The line <code>texture(sTD2DInputs[0], vUV.st)</code>, samples the texture <code>sTD2DInputs[0]</code>, at texture coordinate <code>vUV.st</code>. Since <code>vUV.st</code> changes for every pixel, we'll be sampling a different pixel from the input each time.

To visualize the values for <code>vUV.st</code>, try putting this shader into the GLSL TOP.

   layout(location = 0) out vec4 fragColor;
   void main()
   {
      fragColor = vec4(vUV.s, vUV.t, 0.0, 1.0);
   }

#### Compute Shaders

Compute shaders can sample inputs using the same texture() functions just like pixel shaders. However there is no <code>vUV</code> coordinate available, so coordinates will need to be manually calculated using the <code>gl_GlobalInvocationID</code> and the input texture resolution, available in it's <code>TDTexInfo</code> structure. Alternatively <code>texelFetch</code> can be used which access integer texture coordinates ranging from [0, width - 1] and [0, height - 1].

## Samplers

Samplers are GLSL's name for a texture. Samplers are given to your GLSL program as arrays, split based on the texture's dimensionality (2D, 3D, 2DArray, Cube etc.). You can find out how many of each type are connected to the TOP using these constants:
  TD_NUM_2D_INPUTS
  TD_NUM_3D_INPUTS
  TD_NUM_2D_ARRAY_INPUTS
  TD_NUM_CUBE_INPUTS

If you change the number/type of inputs connected to your GLSL TOP, then the shader will recompile with new values for the above defines and below arrays. Regardless of which input a TOP is connected to, it will be collapse into an array of samplers based on it's dimensionality. The arrays are defined as follows (you don't need to declare these in your shader):

  uniform sampler2D sTD2DInputs[TD_NUM_2D_INPUTS];
  uniform sampler3D sTD3DInputs[TD_NUM_3D_INPUTS];
  uniform sampler2DArray sTD2DArrayInputs[TD_NUM_2D_ARRAY_INPUTS];
  uniform samplerCube sTDCubeInputs[TD_NUM_CUBE_INPUTS];

So for example say you have 5 inputs connected to your GLSL TOP, in this order: a 2D TOP, a 3D TOP, a 2D TOP, a Cube TOP, a 2D Array TOP. Then
  TD_NUM_2D_INPUTS = 2
  TD_NUM_3D_INPUTS = 1
  TD_NUM_2D_ARRAY_INPUTS = 1
  TD_NUM_CUBE_INPUTS = 1

And you can reference your inputs like this:
  texture(sTD2DInputs[0], vUV.st); // first 2D input
  texture(sTD2DInputs[1], vUV.st); // second 2D input, NOT the second input connected to the TOP though
  texture(sTD3DInputs[0], vUV.stp); // first 3D input
  texture(sTDCubeInputs[0], vUV.stp); // first cube input
  texture(sTD2DArrayInputs[0], vUV.stp); // first 2D array input

#### Non-Dynamically Uniform Sampler Access

By default accessing an array of samplers (or image outputs) must be done with what is known as a [https://www.khronos.org/opengl/wiki/Core_Language_(GLSL)#Dynamically_uniform_expression dynamically uniform expression]. This essentially means the array index should be a compile time constant, something the compiler can reduce down to a constant at compile time, or a few other shader inputs, outlined in the previous linked article. A for-loop always going from 0 to 5 for example is something that the compiler knows at compile time, and is thus dynamically uniform. Similarly, a uniform integer value passed into the shader is also dynamically uniform. For GLSL MATs, your Instance ID (TDInstanceID()) is '''not''' dynamically uniform.
If you want to look up into your inputs using something that is decided during shader execution, such as deciding on a different input based on the current UV value, you need to wrap your index in <code>nonuniformEXT()</code> to tell the compiler the index is non-uniform.
E.g
  int inputIndex;
  if (vUV.s > 0.5)
      inputIndex = 0;
  else
      inputIndex = 1;
  vec4 col = sTD2DInputs[nonuniformEXT(inputIndex)], vUV);

### Built In Samplers

For convenience the following samplers are provided for you to use as needed:
  uniform sampler2D sTDNoiseMap;  // A 256x256 8-bit Red-only channel texture that has random data.

  uniform sampler1D sTDSineLookup; // A Red-only texture that goes from 0 to 1 in a sine shape.

## POP Attributes

```glsl
attribType TDBuffer_AttribName(uint elementIndex, uint arrayIndex); //access to POP attribute buffer declared on Buffer Page
TDBuffer_AttribName(uint elementIndex) = TDBuffer_AttribName(elementIndex, 0); //arrayIndex is optional, defaults to 0

const uint TDBufferLength_AttribName(); //length of buffer
const uint cTDBufferArraySize_AttribName; //constant with size of array for array attributes
```

## Uniforms
A uniform is a value that stays the same for every pixel that is drawn. They are set using the Vectors 1 and Vectors 2 pages in the GLSL TOP. To use a uniform inside your shader, declare a uniform of the same name and size as the parameters you have set on the Vectors pages of the GLSL TOP.
For example, lets say we want to make a shader that will create an image that is one solid color, but you don't want it hard coded into the shader (as we did in the first example).

  layout(location = 0) out vec4 fragColor;
  uniform vec4 uColor;
  void main()
  {
     fragColor = uColor;
  }

You can now set the '''Value''' parameters on the GLSL TOP for the '''Uniform Name''' ''uColor'' however you see fit (ie. export to them, use expressions, or set them by hand).  The GLSL TOP will automatically update and create a new image to match the changing values.

### Built in Uniforms

The GLSL TOP has built-in uniforms that may come in useful depending on the shader you are writing. You do not need to declare this uniforms, they are declared for you.

There are many arrays of this structure that gives information about input/output textures such as their resolution. The structure is defined as:

  struct TDTexInfo
  {
    // contains (1.0 / width, 1.0 / height, width, height)
    vec4 res;  
    // contains (1.0 / depth, depth, depthOffset, undefined)
    // depthOffset is between [0,1] for 3D textures and between [0, depth - 1] for 2D texture Arrays.
    vec4 depth;
    
  };

For each of the input sampler arrays (2D, 3D, 2DArray etc.), there is a parallel array of the above structure containing the information about each sampler. For the output info of the texture, there is uTDOutputINfo. You can get the resolution the TOP is going to output at using this uniform. No need to try to pass it in manually via a custom uniform. The depthOffset value will always be 0 though.

  uniform TDTexInfo uTD2DInfos[TD_NUM_2D_INPUTS];
  uniform TDTexInfo uTD3DInfos[TD_NUM_3D_INPUTS];
  uniform TDTexInfo uTD2DArrayInfos[TD_NUM_2D_ARRAY_INPUTS];
  uniform TDTexInfo uTDCubeInfos[TD_NUM_CUBE_INPUTS];
  
  // Information about the output of the TOP such as it's resolution.
  uniform TDTexInfo uTDOutputInfo;

So for example to get the width of the first 2D input, you could type:
  float width = uTD2DInfos[0].res.z; 

When the input is a texture that has depth (3D or 2D Array), then the depth variable will contain the depth, and the depthOffset. The depthOffset is the offset from the texture coordinate at the front of the texture to the texture coordinate of the slice of the input that was most recently updated. So if you wanted a TOP that always output the newest slice of a 3D texture use this shader

```glsl
  layout(location = 0) out vec4 fragColor;
  void main()
  {
      // The center of the first slice is not located at 0, but rather halfway between 0 (the start of the first slice)
      // and 1.0 / depth (the end of the first slice)
      float firstSlice = uTD3DInfos[0].depth.x * 0.5;
      
      // now add the offset
      firstSlice += uTD3DInfos[0].depth.z;
 
      // now sample the texture
      fragColor = texture(sTD3DInputs[0], vec3(vUV.st, firstSlice));
  }
```

For 3D textures the depthOffset is always between 0 and 1.  For 2D Arrays the offset is between 0 and (depth - 1), and will always be an integer.


When outputting a 3D or 2D Array texture, this uniform holds the slice index that you are currently rendering to.

```glsl
// Refer to [[#3D Textures and 2D Texture Arrays |3D Textures and 2D Texture Arrays]]
uniform int uTDCurrentDepth;
```

When using the "Num Passes" parameter on the Common page of the GLSL TOP, it is often useful to know which pass you are currently rendering in the shader. You can do this by looking at the uniform

```glsl
// The current render pass in the GLSL TOP, starts at 0 and counts up.
uniform int uTDPass;
```

## Atomic Counters

Atomic counters are global unsigned integers that can have atomic operations performed on them, namely increment and decrement. They can be used in the shaders at any stage of the pipeline (vertex, fragment/pixel, compute) and can be used to track all sorts of things such as number of vertices, number of red pixels, and more. All shader executions will be using the same variable, which allows them to share information between each other.

Below is a simple example of a pixel shader where the atomic counter is incremented each time (ie. once per pixel), converted to a float, and then put into the red channel. Visually, pixels that are rendered first will be a darker red than those rendered last.

```glsl
uniform atomic_uint ac;
out vec4 fragColor;
void main()
{
  uint c = atomicCounterIncrement(ac);
  float r = (c/255)/255.f;
  fragColor = vec4(r,0,0,1);
}
```

They can also be declared and initialized as arrays by declaring them as:

```glsl
uniform atomic_uint ac[10];
```

Note that although many online examples will prefix the declaration with a binding location such as <code>layout (binding = 0)</code>, it is more efficient to omit that and let our compiler assign the binding automatically.


## Built-in Functions

These are TouchDesigner specific functions which are made available for use within the shader. 
### Output Swizzle
  // Any color value being written to a texture (either through <code>imageStore</code> or an <code>out</code> 
  // variable should be passed through this function to ensure the color channels go to the correct outputs color channels.
  vec4 TDOutputSwizzle(vec4 c);

### Perlin and Simplex Noise

```glsl
// Noise funtcions
// These will return the same result for the same input
// Results are between -1 and 1
// Can be slow so just be aware when using them. 
// Different dimensionality selected by passing vec2, vec3 or vec4. 
float TDPerlinNoise(vec2 v);
float TDPerlinNoise(vec3 v);
float TDPerlinNoise(vec4 v);
float TDSimplexNoise(vec2 v);
float TDSimplexNoise(vec3 v);
float TDSimplexNoise(vec4 v);
```

### HSV Conversion

```glsl
// Converts between RGB and HSV color space
vec3 TDHSVToRGB(vec3 c);
vec3 TDRGBToHSV(vec3 c);
```

### Dithering

```glsl
// Applies a small random noise to the color to help avoid banding
// in some cases.
vec4 TDDither(vec4 color);
```
  
### Matrix Functions

```glsl
// Creates a translation matrix for the given 3 translation values.
mat4 TDTranslate(float x, float y, float z);

// Creates a rotation matrix that rotates around the +X, +Y and +Z axis repectively.
mat3 TDRotateX(float radians);
mat3 TDRotateY(float radians);
mat3 TDRotateZ(float radians);

// Creates a rotation matrix that rotates around the 'axis', the given number of 'radians'
// The 'axis' vector must already be normalized before being passed to this function.
mat3 TDRotateOnAxis(float radians, vec3 axis);

// Creates a scale matrix for the given 3 scale values.
mat3 TDScale(float x, float y, float z);

// Creates a rotation matrix that rotates starting from looking down +Z, to the 'forward' vector direction.
// The 'forward' and 'up' vectors passed to this function do not need to be normalized.
mat3 TDRotateToVector(vec3 forward, vec3 up);

// Creates a rotation matrix to rotate from vector 'from' to vector 'to'. The solution isn't particularly stable, but useful in some cases.
// The 'from' and 'to' vectors must already be normalized before being passed to this function.
mat3 TDCreateRotMatrix(vec3 from, vec3 to);
```

## Sampling more than one pixel

It some shaders you may want to sample more than one pixel from the input TOP (when creating a Blur shader for example). This is done simply with multiple calls to <code>texture()</code>, while offsetting the values of <code>vUV</code> (or your own texture coordinate).

In texture coordinate terms, the value difference between one pixel and the pixel directly to the right of it is (1.0 / width). Similarly, the value difference between one pixel and the pixel directly below it is -(1.0 / height).
The following function is helpful in calculating the correct texture coordinates for neighboring pixels:

```glsl
// This function is not provided for you, you need to declare it yourself.
vec2 input2DOffset(int texIndex, int xOffset, int yOffset)
{
    return vec2(vUV.s + (float(xOffset) * uTD2DInfos[texIndex].res.s),
              vUV.t + (float(yOffset) * uTD2DInfos[texIndex].res.t));
}
```

There is however a new function is GLSL, <code>textureOffset()</code> which does this work for you. It has a limited range it can sample from the starting coordinate though, so it can't be used to get an arbitrary sample offset from a coordinate.

Here is a very simple blur shader that will sample a 3x3 grid around each pixel and output the average value of all 9 pixels. It's manually calculating the offsets instead of using <code>textureOffset</code>, although <code>textureOffset</code> would work fine in this example since the offsets are only 1 pixel.

```glsl
  vec2 input2DOffset(int texIndex, int xOffset, int yOffset)
  {
      return vec2(vUV.s + (float(xOffset) * uTD2DInfos[texIndex].res.s),
                 vUV.t + (float(yOffset) * uTD2DInfos[texIndex].res.t));
  }
  
  layout(location = 0) out vec4 fragColor;
  void main()
  {
      vec4 colorSum = vec4(0.0);
      colorSum += texture(sTD2DInputs[0], input2DOffset(0, 0, 0));
      colorSum += texture(sTD2DInputs[0], input2DOffset(0, -1, -1));
      colorSum += texture(sTD2DInputs[0], input2DOffset(0, 0, -1));
      colorSum += texture(sTD2DInputs[0], input2DOffset(0, 1, -1));
      colorSum += texture(sTD2DInputs[0], input2DOffset(0, 1, 0));
      colorSum += texture(sTD2DInputs[0], input2DOffset(0, 1, 1));
      colorSum += texture(sTD2DInputs[0], input2DOffset(0, 0, 1));
      colorSum += texture(sTD2DInputs[0], input2DOffset(0, -1, 1));
      colorSum += texture(sTD2DInputs[0], input2DOffset(0, -1, 0));
      fragColor = colorSum / 9.0;
  }
```

## 3D Textures and 2D Texture Arrays

### Pixel Shaders
When creating a [[3D Texture]] or a [[2D Texture Array]], your shader will be rendered once for every depth slice that is created. It's like rendering a bunch of 2D textures.

Along with the different input samplers you'll get, you also have access to a few uniforms to help you decide what
to create for each slice.

  uniform int uTDCurrentDepth; // Is the 0-based index of the slice that's currently being created.

### Compute Shaders
When creating a [[3D Texture]] or a [[2D Texture Array]] with a compute shader, the shader is still only ran once. The entire output texture is available to be written to using <code>imageStore</code>, and should be filled as desired, possibly with a Z dispatch size equal to the depth of the texture.

## Outputting to Multiple Color Buffers

In the same pixel shader you can output to multiple identical size/format buffers at the same time. To do this first turn up the "# of Color Buffers" parameter in the [[GLSL TOP]] to the number of outputs you need. 

The output connector on the GLSL TOP will always output the color for the first color buffer. To get the other color buffers use a [[Render Select TOP]] and point it to the [[GLSL TOP]], then select your color buffer index you want.

### Pixel Shaders
In your shader declare your other other output locations. For example if your plan to output to 3 different buffers you could declare them like this:

```glsl
  layout(location = 0) out vec4 fragColor;
  layout(location = 1) out vec4 otherColor;
  layout(location = 2) out vec4 extraInfo;
```

Now you can write to <code>fragColor</code>, <code>otherColor</code> and <code>extraInfo</code> to write to the 3 color buffers that your are outputting to. If you don't write to all of your outputs in all cases, the resulting pixel value is undefined. Don't avoid writing a value to try to keep last frame's value in the buffer.

### Compute Shaders

The <code>sTDComputeOutputs[]</code> uniform will be sized equal to the number of color buffers being output.

## Vertex Shader

In most cases you will not need to provide a vertex shader to the GLSL TOP. If you decide to provide a vertex shader, it's most basic form would be:

```glsl
  out vec3 texCoord;
  void main()
  {
       texCoord = uv[0];
       gl_Position = TDSOPToProj(vec4(P, 1.0));
  }
```

It is very important that you do not manipulate the vertex position, as it will cause the quad to not be aligned with the TOP output. Also, notice how we declare our own output variable for the texture coordinate here. <code>vUV</code> will not be automatically available to us in the pixel shader if we supply a vertex shader, so we use this variable instead;

```glsl
  layout (location = 0) out vec4 fragColor;
  in vec3 texCoord;
  void main()
  {
      fragColor = texture(sTD2DInputs[0], texCoord.st);
  }
```

## Debugging Crashes

With the changeover to Vulkan, it's much easier for incorrectly written GLSL to cause a full application crash. For more information about this, refer to [[Debugging crashes triggered by GLSL errors|this article.]]

## Other Notes

### #version statement

TouchDesigner will automatically put a #version statement at the start of the shaders when compiling them, so you should make sure your shaders don't have a #version statement. You will get an error if they do.

## GLSL Matrix Functions

From: https://docs.derivative.ca/GLSL_Matrix_Functions

```glsl
// Creates a translation matrix for the given 3 translation values.
mat4 TDTranslate(float x, float y, float z);

// Creates a rotation matrix that rotates around the +X, +Y and +Z axis repectively.
mat3 TDRotateX(float radians);
mat3 TDRotateY(float radians);
mat3 TDRotateZ(float radians);

// Creates a rotation matrix that rotates around the 'axis', the given number of 'radians'
// The 'axis' vector must already be normalized before being passed to this function.
mat3 TDRotateOnAxis(float radians, vec3 axis);

// Creates a scale matrix for the given 3 scale values.
mat3 TDScale(float x, float y, float z);

// Creates a rotation matrix that rotates starting from looking down +Z, to the 'forward' vector direction.
// The 'forward' and 'up' vectors passed to this function do not need to be normalized.
mat3 TDRotateToVector(vec3 forward, vec3 up);

// Creates a rotation matrix to rotate from vector 'from' to vector 'to'. The solution isn't particularly stable, but useful in some cases.
// The 'from' and 'to' vectors must already be normalized before being passed to this function.
mat3 TDCreateRotMatrix(vec3 from, vec3 to);
```
