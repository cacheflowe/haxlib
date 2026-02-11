import numpy
import cv2
import base64

def base64_from_top(top, ext='.jpg'):
	# From TDcomfyEXT.py
	# get the image data from the TOP in 255 range from normalized
	image = top.numpyArray(delayed=False) * 255
	image = numpy.flipud(image).astype(numpy.uint8)

	# Check if the image has an alpha channel
	if image.shape[2] == 4:
		image = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
	else:
		image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

	# ask for jpg encoding
	imageData = cv2.imencode(ext, image)[1].tobytes()
	return str(base64.b64encode(imageData), "utf-8")


def base64_from_image_file(imagePath):
	# check whether file exists
	if not os.path.exists(imagePath):
		print('[ImageUtil] Error: Image file not found:', imagePath)
		return "Error: Image file not found"

	# convert image to base64 string
	with open(imagePath, "rb") as imageFile:
		base64Str = base64.b64encode(imageFile.read())
		base64Str = base64Str.decode('utf-8')
		return base64Str
