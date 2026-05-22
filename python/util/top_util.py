import td

def aspect_ratio(opPath):
	"""Returns the aspect ratio (width/height) of a TOP. If height is 1, the width is the aspect ratio. Multiply as needed."""
	return op(opPath).width / op(opPath).height


# ── Resolution & Dimensions ──────────────────────────────────

def resolution(opPath):
	"""Returns (width, height) tuple of a TOP."""
	op: td.OP = op(opPath)
	return (op.width, op.height)


def pixel_count(opPath):
	"""Total number of pixels in a TOP."""
	op: td.OP = op(opPath)
	return op.width * op.height


# ── Memory & Format ──────────────────────────────────────────

def gpu_memory_mb(opPath):
	"""GPU memory usage of a TOP in megabytes."""
	return op(opPath).gpuMemory / (1024 * 1024)


def pixel_format(opPath):
	"""Returns the pixel format menu name (suitable for Python/parm use)."""
	return op(opPath).pixelFormatName


def is_hdr(opPath):
	"""Check if a TOP is using a floating-point (HDR) pixel format."""
	fmt = op(opPath).pixelFormatName
	return '16float' in fmt or '32float' in fmt


# ── Sampling ─────────────────────────────────────────────────

def sample_pixel(opPath, x, y):
	"""Sample RGBA color at pixel coordinates. Returns (r, g, b, a).
	WARNING: expensive - stalls GPU. Use for debugging only."""
	return op(opPath).sample(x=x, y=y)


def sample_uv(opPath, u, v):
	"""Sample RGBA color at normalized UV coordinates. Returns (r, g, b, a).
	WARNING: expensive - stalls GPU. Use for debugging only."""
	return op(opPath).sample(u=u, v=v)


def sample_center(opPath):
	"""Sample RGBA color at the center of a TOP."""
	return op(opPath).sample(u=0.5, v=0.5)


def sample_brightness(opPath, u=0.5, v=0.5):
	"""Sample perceived brightness (luminance) at a UV position.
	Uses standard Rec. 709 coefficients."""
	r, g, b, a = op(opPath).sample(u=u, v=v)
	return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ── Export / Conversion ──────────────────────────────────────

def save_image(opPath, filepath, quality=1.0, createFolders=True):
	"""Save TOP to an image file (.png, .jpg, .exr, .tiff, .bmp, .dds).
	Returns the FileSaveStatus object."""
	return op(opPath).save(filepath, createFolders=createFolders, quality=quality)


def save_image_async(opPath, filepath, quality=1.0, createFolders=True):
	"""Save TOP to an image file asynchronously. Returns FileSaveStatus
	(query .isCompleted() to check status)."""
	return op(opPath).save(filepath, asynchronous=True, createFolders=createFolders, quality=quality)


def to_numpy(opPath, delayed=False):
	"""Get TOP image as a numpy array. Pixels addressed as [h, w].
	Set delayed=True to avoid GPU stalls (returns None until next call)."""
	return op(opPath).numpyArray(delayed=delayed)


def to_byte_array(opPath, filetype='.png', quality=1.0):
	"""Get TOP image as a bytearray in the given file format."""
	return op(opPath).saveByteArray(filetype, quality=quality)


# ── Cook Info ────────────────────────────────────────────────

def cook_time_ms(opPath):
	"""Last CPU cook time of a TOP in milliseconds."""
	return op(opPath).cpuCookTime


def gpu_cook_time_ms(opPath):
	"""Last GPU cook time of a TOP in milliseconds."""
	return op(opPath).gpuCookTime


def total_cooks(opPath):
	"""Total number of times a TOP has cooked."""
	return op(opPath).totalCooks

