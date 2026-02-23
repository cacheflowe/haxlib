
# from https://gist.github.com/th0ma5w/9883420
# updated by @cacheflowe

"""
t is the current time (or position) of the tween.
b is the beginning value of the property.
c is the change between the beginning and destination value of the property.
d is the total time of the tween.
"""

import math

linearTween = lambda t, b, c, d : c*t/d + b
linearTweenNorm = lambda t : linearTween(t, 0, 1, 1)

def easeInQuad(t, b, c, d):
	t /= d
	return c*t*t + b

def easeInQuadNorm(t):
	return easeInQuad(t, 0, 1, 1)

def easeOutQuad(t, b, c, d):
	t /= d
	return -c * t*(t-2) + b

def easeOutQuadNorm(t):
	return easeOutQuad(t, 0, 1, 1)

def easeInOutQuad(t, b, c, d):
	t /= d/2
	if t < 1:
		return c/2*t*t + b
	t-=1
	return -c/2 * (t*(t-2) - 1) + b

def easeInOutQuadNorm(t):
	return easeInOutQuad(t, 0, 1, 1)


def easeInOutCubic(t, b, c, d):
	t /= d/2
	if t < 1:
		return c/2*t*t*t + b
	t -= 2
	return c/2*(t*t*t + 2) + b

def easeInOutCubicNorm(t):
	return easeInOutCubic(t, 0, 1, 1)

def easeInQuart(t, b, c, d):
	t /= d
	return c*t*t*t*t + b

def easeInQuartNorm(t):
	return easeInQuart(t, 0, 1, 1)

def easeOutQuart(t, b, c, d):
	t /= d
	t -= 1
	return -c * (t*t*t*t - 1) + b

def easeOutQuartNorm(t):
	return easeOutQuart(t, 0, 1, 1)

def easeInOutQuart(t, b, c, d):
	t /= d/2
	if t < 1:
		return c/2*t*t*t*t + b
	t -= 2
	return -c/2 * (t*t*t*t - 2) + b

def easeInOutQuartNorm(t):
	return easeInOutQuart(t, 0, 1, 1)

def easeInQuint(t, b, c, d):
	t /= d
	return c*t*t*t*t*t + b

def easeInQuintNorm(t):
	return easeInQuint(t, 0, 1, 1)

def easeOutQuint(t, b, c, d):
	t /= d
	t -= 1
	return c*(t*t*t*t*t + 1) + b

def easeOutQuintNorm(t):
	return easeOutQuint(t, 0, 1, 1)

def easeInOutQuint(t, b, c, d):
	t /= d/2
	if t < 1:
		return c/2*t*t*t*t*t + b
	t -= 2
	return c/2*(t*t*t*t*t + 2) + b

def easeInOutQuintNorm(t):
	return easeInOutQuint(t, 0, 1, 1)

def easeInSine(t, b, c, d):
	return -c * math.cos(t/d * (math.pi/2)) + c + b

def easeInSineNorm(t):
	return easeInSine(t, 0, 1, 1)

def easeOutSine(t, b, c, d):
	return c * math.sin(t/d * (math.pi/2)) + b

def easeOutSineNorm(t):
	return easeOutSine(t, 0, 1, 1)

def easeInOutSine(t, b, c, d):
	return -c/2 * (math.cos(math.pi*t/d) - 1) + b

def easeInOutSineNorm(t):
	return easeInOutSine(t, 0, 1, 1)

def easeInExpo(t, b, c, d):
	return c * math.pow( 2, 10 * (t/d - 1) ) + b

def easeInExpoNorm(t):
	return easeInExpo(t, 0, 1, 1)

def easeOutExpo(t, b, c, d):
	return c * ( -math.pow( 2, -10 * t/d ) + 1 ) + b

def easeOutExpoNorm(t):
	return easeOutExpo(t, 0, 1, 1)

def easeInOutExpo(t, b, c, d):
	if t == 0:
		return b
	if t == d:
		return b + c
	t /= d/2
	if t < 1: 
		return c/2 * math.pow( 2, 10 * (t - 1) ) + b
	t -= 1
	return c/2 * ( -math.pow( 2, -10 * t) + 2 ) + b

def easeInOutExpoNorm(t):
	return easeInOutExpo(t, 0, 1, 1)

def easeInCirc(t, b, c, d):
	t /= d
	return -c * (math.sqrt(1 - t*t) - 1) + b

def easeInCircNorm(t):
	return easeInCirc(t, 0, 1, 1)

def easeOutCirc(t, b, c, d):
	t /= d
	t -= 1
	return c * math.sqrt(1 - t*t) + b

def easeOutCircNorm(t):
	return easeOutCirc(t, 0, 1, 1)

def easeInOutCirc(t, b, c, d):
	t /= d/2
	if t < 1:
		return -c/2 * (math.sqrt(1 - t*t) - 1) + b
	t -= 2
	return c/2 * (math.sqrt(1 - t*t) + 1) + b

def easeInOutCircNorm(t):
	return easeInOutCirc(t, 0, 1, 1)