
// Vertical Gaussian Blur - 9-tap kernel (sigma 2.7)
// For two-pass blur, use a second GLSL TOP with horizontal sampling.

uniform float uAmplitude;  // blur spread multiplier (default: 1.0)

out vec4 fragColor;
void main()
{
	// Compute texel step once up front
	vec2 step = vec2(uTD2DInfos[0].res.s, uTD2DInfos[0].res.t) * uAmplitude;

	// 9-tap Gaussian kernel, sigma = 2.7
	vec4 sum = vec4(0.0);
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -4.0 * step.t)) * 0.051;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -3.0 * step.t)) * 0.0918;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -2.0 * step.t)) * 0.12245;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -1.0 * step.t)) * 0.1531;
	sum += texture(sTD2DInputs[0], vUV.st)                             * 0.1633;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  1.0 * step.t)) * 0.1531;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  2.0 * step.t)) * 0.12245;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  3.0 * step.t)) * 0.0918;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  4.0 * step.t)) * 0.051;

	fragColor = TDOutputSwizzle(sum);
}