uniform float uAlphaStep;

out vec4 fragColor;
void main()
{
	// Premultiplied alpha: adjust alpha and scale RGB proportionally.
	// Compositing: col = bac*(1.0-spr.a) + spr.rgb  (RGB already carries alpha)
	// https://www.shadertoy.com/view/cds3z7
	// https://iquilezles.org/articles/premultipliedalpha/
	vec4 color = texture(sTD2DInputs[0], vUV.st);
	float newAlpha = clamp(color.a + uAlphaStep, 0.0, 1.0);
	float scale = color.a > 0.0 ? newAlpha / color.a : 0.0;
	color = vec4(color.rgb * scale, newAlpha);
	fragColor = TDOutputSwizzle(color);
}
