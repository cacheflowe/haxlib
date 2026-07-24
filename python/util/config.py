import sys
import os
import glob
import importlib
import platform
import td
from typing import Any

def register_singleton(instance: Any, module_name: str) -> Any:
	"""Bridge a TD extension singleton into sys.modules so external imports find it.

	TD loads extensions in its own execution context, separate from Python's import
	system. Returns the instance so it can be used as a one-liner assignment:
	  MyClass.i = config.register_singleton(instance, 'MyModule')
	"""
	mod = sys.modules.get(module_name)
	if mod is not None:
		cls = getattr(mod, type(instance).__name__, None)
		if cls is not None:
			cls.i = instance
	return instance

def PrintPythonPath():
	print("[Config] 🐍----------------------------------🐍")
	print('[Config] Python sys.path:')
	for path in sys.path:
		print("[Config] -", path)
	print("[Config] 🐍----------------------------------🐍")


def AddCondaEnvToPath(user, env_name):
	if platform.system() == 'Windows':
		windowsPathBase = 'C:/Users/'+user+'/miniconda3/envs/'+env_name
		windowsPathDLLs = windowsPathBase+'/DLLs'
		windowsPathLib = windowsPathBase+'/Library/bin'
		windowsPathSite = windowsPathBase+'/Lib/site-packages'
		if windowsPathSite not in sys.path:
			print(f"[Config] Adding conda environment '{env_name}' for user '{user}' to sys.path")
			print('[Config] Added Conda DLLs and Library paths added to sys.path:')
			print('[Config] - Conda env DLLs path: ', windowsPathDLLs)
			print('[Config] - Conda env Library path: ', windowsPathLib)
			print('[Config] - Conda env site-packages path: ', windowsPathSite)
			os.add_dll_directory(windowsPathDLLs)
			os.add_dll_directory(windowsPathLib)
			sys.path.insert(0, windowsPathSite)  # Add to the beginning of the path list
		else:
			print('[Config] Conda env {} already loaded!'.format(env_name))
	else:
		print(f"[Config] Adding conda environment '{env_name}' for user '{user}' to sys.path")
		macPathBase = '/Users/'+user+'/opt/miniconda3/envs/'+env_name
		macPathLib = macPathBase+'/lib'
		macPathBin = macPathBase+'/bin'
		macPathSite = macPathBase+'/lib/python3.9/site-packages'
		if macPathSite not in sys.path:
			print('[Config] Added Conda lib, bin and site-packages paths to sys.path:')
			print('[Config] - Conda env lib path: ', macPathLib)
			print('[Config] - Conda env bin path: ', macPathBin)
			print('[Config] - Conda env site-packages path: ', macPathSite)
			os.environ['PATH'] = macPathLib + os.pathsep + os.environ['PATH']
			os.environ['PATH'] = macPathBin + os.pathsep + os.environ['PATH']
			sys.path.insert(0, macPathSite)  # Add to the beginning of the path list
		else:
			print('[Config] Conda env {} already loaded!'.format(env_name))


def AddPyDirToPath(new_path):
	if new_path not in sys.path:
		if os.path.exists(new_path):
			sys.path.insert(0, new_path)  # Add to the beginning of the path list
	else:
		print('[Config] Python path already loaded!')


def LoadEnvFile(new_path=os.path.join(td.project.folder, '.env')):
	# load environment variables from a .env file and copy values into AppStore
	if os.path.exists(new_path):
		print(f"[Config] Loading .env file: {new_path}")
		with open(new_path) as f:
			for line in f:
				line = line.strip()
				if line and not line.startswith("#"):
					key, value = line.split("=", 1)
					os.environ[key] = value
					print(f"[Config] - {key}={value}")
					if td.op.AppStore:
						td.op.AppStore.SetFromString(key, value)
	else:
		print(f"[Config] Env file {new_path} does not exist!")


def LoadSystemEnvironmentVar(key, default_value=None):
	if not td.op.AppStore:
		print("[Config] AppStore not available.")
		return
	if key not in os.environ:
		print(f"[Config] System environment variable '{key}' not found. Using default value: {default_value}")
		td.op.AppStore.SetFromString(key, default_value)
	else:
		value = os.environ[key]
		if value is not None:
			print(f"[Config] Add system environment var: {key}={value}")
			td.op.AppStore.SetFromString(key, value)


def ReloadModules():
	tdTypes = {k: v for k, v in vars(td).items() if not k.startswith('_')}
	reloaded = []
	skipped = []
	subdirs = ['python', 'python/util', 'python/app', 'python/net']
	for subdir in subdirs:
		for filepath in glob.glob(os.path.join(td.project.folder, subdir, '*.py')):
			modName = os.path.splitext(os.path.basename(filepath))[0]
			if modName.startswith('_') or modName in ('App'):
				continue
			try:
				if modName in sys.modules:
					sys.modules[modName].__dict__.update(tdTypes)
					importlib.reload(sys.modules[modName])
					reloaded.append(modName)
				else:
					importlib.import_module(modName)
					reloaded.append(modName)
			except ModuleNotFoundError as e:
				print(f'[Config] Skipping {modName}: {e}')
				skipped.append(modName)
			except BaseException:
				print(f'[Config] Error reloading module {modName}:', sys.exc_info()[0], sys.exc_info()[1])
				skipped.append(modName)
	reloaded_list = '\n'.join(f'  - {m}' for m in reloaded)
	print(f'[Config] Reloaded:\n{reloaded_list}')
	if skipped:
		skipped_list = '\n'.join(f'  - {m}' for m in skipped)
		print(f'[Config] Skipped:\n{skipped_list}')
	return reloaded, skipped