import tdu

class Colors:
	"""
	Colors description
	"""
	def __init__(self, ownerComp):
		self.ownerComp = ownerComp
		self.RebuildColors()


	def ColorNameToParName(self, colorName):
		colorName = colorName.replace('_', '')
		return colorName[0].upper() + colorName[1:].lower()


	def RebuildColors(self):
		# build COMP pars
		self.ownerComp.par.opviewer = './container1' 
		self.ownerComp.destroyCustomPars()
		newPage = self.ownerComp.appendCustomPage('Colors List')
		newPage.appendPulse('Init', label='Re-init colors')

		# read colors from input DAT
		self.colors = {}
		for row in self.ownerComp.op('in_colors').rows():
			# parse table
			colorNameOrig = row[0].val  # original color name with underscores
			colorName = colorNameOrig.replace('_', '').strip()  # remove underscores and whitespace
			colorNameCamel = colorName[0].upper() + colorName[1:].lower()
			sourceHex = row[1].val

			# check for color components option (3-4 normalized numbers, comma-delimited)
			# if the sourceHex contains commas, it is a list of RGB(A) values
			if sourceHex.find(',') >= 0:
				sourceHex = sourceHex.split(',')
				sourceHex = [float(c.strip()) for c in sourceHex] # remove whitespace and convert to float
				if len(sourceHex) == 3:
					sourceHex.append(1.0)  # add alpha channel if not present
				sourceHex = self.RGBA2Hex(sourceHex)  # convert to hex string

			# normalize hex strings and add alpha channel if needed
			sourceHex = sourceHex.lower()
			sourceHex = sourceHex.strip()  # remove leading/trailing whitespace
			sourceHex = sourceHex.lstrip('#')  # remove leading '#'
			if len(sourceHex) == 6:  # if the hex string is 6 characters long, add alpha channel
				sourceHex += 'ff'
			finalHex = sourceHex

			# convert hex to normalized RGBA tuple
			# round to 3 decimal places
			# convert to Color object - https://docs.derivative.ca/Color_Class
			color = self.Hex2RGBA(finalHex)
			color = tuple(round(c, 3) for c in color)
			colorObj = tdu.Color(color)

			# create color parameters on component for visibility
			# newPage.appendHeader(colorNameCamel+'header', label=colorNameOrig)

			colorPar = newPage.appendRGBA(self.ColorNameToParName(colorNameCamel), label=colorNameCamel)
			colorPar[0].val = color[0]
			colorPar[1].val = color[1]
			colorPar[2].val = color[2]
			colorPar[3].val = color[3]
			colorPar.readOnly = True

			colorHexPar = newPage.appendStr(self.ColorNameToParName(colorNameCamel) + 'hex', label=colorNameCamel + ' (Hex)')
			colorHexPar.val = '#'+finalHex
			colorHexPar.readOnly = True

			# store color info in dictionary for Get() method
			self.colors[colorNameOrig] = {
				'hex': finalHex,
				'rgb': color,
				'colorObj': colorObj,
				'par': colorPar
			}

		# write out output table
		outTable = self.ownerComp.op('table_colors_converted')
		outTable.clear()
		outTable.appendRow(['Color Name', 'hex', 'r', 'g', 'b', 'a'])
		for colorName, colorInfo in self.colors.items():
			hexColor = colorInfo['hex']
			r, g, b, a = colorInfo['rgb']
			outTable.appendRow([colorName, hexColor, r, g, b, a])

		# re-clone replicator	
		replicator = self.ownerComp.op('container1/replicator1')
		replicator.par.recreateall.pulse()


	def Get(self, colorName):
		return self.colors[colorName]['colorObj']

	def GetHex(self, colorName):
		return self.colors[colorName]['hex']

	def Hex2RGBA(self, hex_string):
		return tuple(int(hex_string[i:i+2], 16) / 255.0 for i in (0, 2, 4, 6))

	def RGBA2Hex(self, rgba):
		# convert RGBA tuple to hex string
		return '#{:02x}{:02x}{:02x}{:02x}'.format(int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255), int(rgba[3] * 255))

	def WriteStopsToRampTableHex(self, rampDAT, gradient):
		rampDAT.clear()
		rampDAT.appendRow(["pos", "r", "g", "b", "a"])
		for stop in gradient:
			percent = stop[0] / 100.0
			hex = stop[1]
			r = round(int(hex[0:2], 16) / 255.0, 3)
			g = round(int(hex[2:4], 16) / 255.0, 3)
			b = round(int(hex[4:6], 16) / 255.0, 3)
			a = 1.0
			rampDAT.appendRow([percent, r, g, b, a])
