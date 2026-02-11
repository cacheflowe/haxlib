
// Alpha step fragment shader
// For feedback alpha reduction down to zero
// Needs a math TOP after the feedback to "premultiply RGB by Alpha"

uniform float uStep; // 0.004

out vec4 fragColor;
void main()
{
	vec4 color = texture(sTD2DInputs[0], vUV.st);
	if(color.a > 0.) {
		color.a -= uStep;
	}
	fragColor = TDOutputSwizzle(color);
}
