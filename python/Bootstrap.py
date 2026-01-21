import os
import sys

config = op.PyUtils.mod('config')

class Bootstrap:
	"""
	Bootstrap Extension Class

	- Add local python moduls path to sys.path for imports
	- Reloads imports for development convenience
	- Loads environment variables from .env file 
	- Loads environment variables from shell script during autmoated launches
	- Loads python modules that were installed locally, or conda envs as needed
	"""
	def __init__(self, ownerComp):
		# The component to which this extension is attached
		self.ownerComp = ownerComp
		print("[Bootstrap] Starting...")
		# self.addPythonUtilsPath()
		# self.reloadImports()
		self.loadEnvVars()
		self.loadPythonModules()
		print("[Bootstrap] Complete!") 

	# Reloads imported Python modules to ensure any changes are applied
	# This is useful during development when you want to see changes without restarting the project.
	# Note: This is not needed in production code
	# def reloadImports(self):
	# 	import config
	# 	importlib.reload(config)

	# Add the path to the Python utils directory to sys.path
	# This allows importing modules from that directory
	# and ensures that the utils are available for use in the project.
	# def addPythonUtilsPath(self):
	# 	print('[Bootstrap] Adding Python utils path to sys.path')
	# 	utils_path = os.path.join(project.folder, 'python', 'util')
	# 	if utils_path not in sys.path:
	# 		sys.path.append(utils_path)

	def loadEnvVars(self):
		# import config
		# Make sure AppStore has the latest defaults set before loading env vars that could override them
		op.AppStore.par.Applydefaults.pulse()
		# Load .env file and system environment vars
		# The order here would override any loaded vars with the last loaded value
		envFilePath = os.path.join(project.folder, '.env')  # path to the .env file
		# defaults to loading the .env file in the project root, but an optional path can be passed in
		config.LoadEnvFile(envFilePath)
		# set by a shell script before launching the .toe: `set sys_env_var=Something`
		# config.LoadSystemEnvironmentVar('sys_env_var', 'Default Value')

	def loadPythonModules(self):
		# import config
		# Add any extra python environments/modules
		# config.AddPyDirToPath(os.path.join(project.folder, 'python', 'other_modules')) # add more python modules to sys.path if desired
		# config.AddCondaEnvToPath("cacheflowe", "td-onnx")
		# config.AddPyDirToPath(os.path.join(project.folder, 'python', '_local_modules'))
		# config.PrintPythonPath()
		return