
// Chladni pattern shader
// by @jorgemoag - https://www.shadertoy.com/view/WdKXRV
// references:
// https://thelig.ht/chladni/
// https://paulbourke.net/geometry/chladni/

uniform float uZoom;      // default: 2.0
uniform float uThickness; // default: 0.1
uniform vec4 uConfig;     // default: vec4(1.0, 1.0, 7.0, 2.0)

#define PI     3.14159265358
#define TWO_PI 6.28318530718

out vec4 fragColor;

void main() {
  // Center UVs and correct for aspect ratio
  vec2 uv = vUV.st - vec2(0.5);
  uv.x *= uTDOutputInfo.res.w / uTDOutputInfo.res.z;
  uv *= uZoom;

  // Animate between two sets of parameters
  float a = uConfig.x;
  float b = uConfig.y;
  float n = uConfig.z;
  float m = uConfig.w;

  // Chladni equation
  float maxAmp = abs(a) + abs(b);
  float amp = a * sin(PI * n * uv.x) * sin(PI * m * uv.y) +
              b * sin(PI * m * uv.x) * sin(PI * n * uv.y);

  // Step function for line thickness
  float col = step(abs(amp), uThickness);
  fragColor = TDOutputSwizzle(vec4(vec3(col), 1.0));
}
