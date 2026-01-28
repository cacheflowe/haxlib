import PIL
from PIL import Image
import numpy as np
from escpos.printer import Network

class EpsonThermalPrint:
	"""
	EpsonThermalPrint 

	install: pip install python-escpos
	
	Docs: https://python-escpos.readthedocs.io/en/latest/api/escpos.html

	"""
	def __init__(self, ownerComp):
		self.ownerComp = ownerComp
		self.opCache = self.ownerComp.op('cache1')
		self.topData = None

	def PrintInputTOP(self):
		self.opCache.par.activepulse.pulse()
		# delay to allow cached image to be ready
		run(lambda: self.PrintInputTOPImmediate(), delayFrames=1)

	def PrintInputTOPImmediate(self):
		# get numpy array from TOP
		self.topData = self.opCache.numpyArray(delayed=False)

		# Convert from float to uint8
		if self.topData.dtype == np.float32 or self.topData.dtype == np.float64:
			self.topData = (self.topData * 255).astype(np.uint8)

		# Create PIL Image from numpy array
		# and fix orientation (TouchDesigner numpyArray is bottom-left origin)
		pilImage = Image.fromarray(self.topData)
		pilImage = pilImage.transpose(PIL.Image.FLIP_TOP_BOTTOM)

		self.PrintImageData(pilImage)

	def PrintImageFromDisk(self, filePath):
		pilImage = Image.open(filePath)
		self.PrintImageData(pilImage)
	
	def PrintImageData(self, pilImage):
		# Handle transparency: Composite over white background if RGBA
		if pilImage.mode == 'RGBA':
			background = Image.new('RGB', pilImage.size, (255, 255, 255))
			background.paste(pilImage, mask=pilImage.split()[3])
			pilImage = background

		# Optional: Convert to grayscale for thermal printer
		pilImage = pilImage.convert('L')

		# Resize to printer width if needed
		printer_width = 500  # Adjust based on your printer's capabilities
		width_percent = (printer_width / float(pilImage.size[0]))
		height = int((float(pilImage.size[1]) * float(width_percent)))
		pilImage = pilImage.resize((printer_width, height), PIL.Image.LANCZOS)

		# Send image to printer
		self.printer = Network(self.ownerComp.par.Printeripaddress.eval(), profile="TM-T88III")  # Even though it's actually a T88VI
		self.printer.image(pilImage, impl='bitImageRaster')

		# finish!
		self.CompletePrintJob()

	def PrintInputDAT(self):
		self.printer = Network(self.ownerComp.par.Printeripaddress.eval(), profile="TM-T88III")  # Even though it's actually a T88VI
		
		# Get input text and split into lines
		text = op('in2').text
		lines = text.split('\n')
		
		# Process each line for markdown formatting
		for line in lines:
			stripped = line.strip()
			
			# Skip empty lines
			if not stripped:
				self.printer.text("\n")
				continue
			
			# Calculate indentation (leading whitespace)
			indent = len(line) - len(line.lstrip())
			indent_str = " " * indent
			
			# Header 1 (# )
			if stripped.startswith('# ') and not stripped.startswith('## '):
				self.printer.set(bold=True, double_height=True, double_width=True)
				self.printer.text(stripped[2:] + "\n")
				self.printer.set(normal_textsize=True)
			
			# Header 2 (## )
			elif stripped.startswith('## ') and not stripped.startswith('### '):
				self.printer.set(bold=True, double_width=True)
				self.printer.text(stripped[3:] + "\n")
				self.printer.set(normal_textsize=True, bold=False)
			
			# Header 3 (### )
			elif stripped.startswith('### '):
				self.printer.set(bold=True, underline=1)
				self.printer.text(stripped[4:] + "\n")
				self.printer.set(bold=False, underline=0)
			
			# Bullet points (- or *)
			elif stripped.startswith('- ') or stripped.startswith('* '):
				self.printer.set(normal_textsize=True)
				self.printer.text(indent_str + "• " + stripped[2:] + "\n")
			
			# Normal paragraph text
			else:
				self.printer.set(normal_textsize=True)
				self.printer.text(stripped + "\n")
		
		self.CompletePrintJob()

	def PrintInputDATSimple(self):
		self.printer = Network(self.ownerComp.par.Printeripaddress.eval(), profile="TM-T88III")  # Even though it's actually a T88VI
		self.printer.text(op('in2').text + "\n")
		# self.printer.writelines('Big line\\n', font='b')
		self.CompletePrintJob()

	def CompletePrintJob(self):
		# close connection or it'll hang and have a timeout before it's usable again!
		self.printer.print_and_feed(1)
		self.printer.cut()
		self.printer.close() 

	def onDestroyTD(self):
		return

	def onInitTD(self):
		return