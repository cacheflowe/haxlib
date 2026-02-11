
// from: https://blog.frost.kiwi/GLSL-noise-and-radial-gradient/

uniform float uAmplitudeNoise; // 13
uniform float uAmplitudeTriangle; // 0.25

out vec4 fragColor;

/* http://www.iryoku.com/next-generation-post-processing-in-call-of-duty-advanced-warfare */
/* Gradient noise from Jorge Jimenez's presentation: */
float gradientNoise(in vec2 uv) {
	return fract(52.9829189 * fract(dot(uv, vec2(0.06711056, 0.00583715))));
}

// Gold Noise (static procedural blue-noise-like distribution)
// Much more organic/random looking than gradient noise
float gold_noise(in vec2 xy, in float seed){
    return fract(tan(distance(xy*1.61803398874989484820459, xy)*seed)*xy.x);
}

// Gold Noise Dither (High frequency, organic grain - Blue Noise approximation)
vec3 GoldNoiseDither(vec2 uv) {
    // Use different seeds for RGB to decorrelate channels (Chromatic Noise)
    float r = gold_noise(uv, 1.0);
    float g = gold_noise(uv, 2.0);
    float b = gold_noise(uv, 3.0);
    
    // Remap [0, 1] -> [-0.5, 0.5]
    vec3 noise = vec3(r, g, b) - 0.5;
		noise = clamp(noise, -0.5, 0.5);
    
    // Adjust strength here (e.g. 4.0 / 255.0 for strong grain)
    return noise * (uAmplitudeNoise / 255.0);
}

// Triangular Dither (removes banding with less perceivable noise than uniform)
vec3 TriangleDither(vec2 uv) {
    float n1 = gradientNoise(uv);
    float n2 = gradientNoise(uv + vec2(5.2, 1.3)); // Offset for independence
    float tri = n1 + n2 - 1.0; // Range [-1.0, 1.0], Triangular PDF
    // Increase the divisor or multiplier to crank up the noise. 
    // 3.0 / 255.0 gives 3 bits of noise, much stronger grain.
    return vec3(tri * (64.0 / 255.0)); 
}

void main()
{
	// Map vUV to uv variable expected by the snippet
	vec2 uv = vUV.st;
	
	// Original logic
	vec3 bgcolor = texture(sTD2DInputs[0], uv).rgb;

	// Apply Gold Noise Dither for organic film grain look
	bgcolor += GoldNoiseDither(gl_FragCoord.xy);
	// Apply triangular dither to further reduce banding
	bgcolor += TriangleDither(gl_FragCoord.xy) * uAmplitudeTriangle;

	// Clamp to prevent wrapping artifacts (sparse off-color dots) from noise overflow
	bgcolor = clamp(bgcolor, 0.0, 1.0);

	// Output using TD output swizzle for correct format support
	// Note: TDDither is internal 8-bit dither, usually redundant if we apply our own better one.
	fragColor = TDOutputSwizzle(vec4(bgcolor, 1.0));
}



