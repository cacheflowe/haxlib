
// Vertical Gaussian Blur - 17-tap kernel (sigma 4.0)
// More samples = smoother falloff at high amplitudes.
// For two-pass blur, use a second GLSL TOP with horizontal sampling.

uniform float uAmplitude;  // blur spread multiplier (default: 1.0)

out vec4 fragColor;
void main()
{
	// Compute texel step once up front
	vec2 step = vec2(uTD2DInfos[0].res.s, uTD2DInfos[0].res.t) * uAmplitude;

	// 17-tap Gaussian kernel, sigma = 4.0
	vec4 sum = vec4(0.0);
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -8.0 * step.t)) * 0.01396;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -7.0 * step.t)) * 0.02230;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -6.0 * step.t)) * 0.03349;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -5.0 * step.t)) * 0.04723;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -4.0 * step.t)) * 0.06256;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -3.0 * step.t)) * 0.07787;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -2.0 * step.t)) * 0.09103;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0, -1.0 * step.t)) * 0.09998;
	sum += texture(sTD2DInputs[0], vUV.st)                                   * 0.10315;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  1.0 * step.t)) * 0.09998;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  2.0 * step.t)) * 0.09103;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  3.0 * step.t)) * 0.07787;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  4.0 * step.t)) * 0.06256;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  5.0 * step.t)) * 0.04723;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  6.0 * step.t)) * 0.03349;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  7.0 * step.t)) * 0.02230;
	sum += texture(sTD2DInputs[0], vUV.st + vec2(0.0,  8.0 * step.t)) * 0.01396;

	fragColor = TDOutputSwizzle(sum);
}