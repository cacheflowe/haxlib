import td
import os

def inspect_property(name, obj, verbose=False):
	print(f"===============================")
	print(f"Object inspection: {name}")
	print(f"Type: {type(obj)}")
	print(f"-------------------------------")
	for prop in dir(obj):
		try:
			isPrivate = prop.startswith('_')
			privateStr = 'private ' if isPrivate else 'public '
			if not verbose:
				privateStr = ''
			value = getattr(obj, prop)
			isFunction = callable(value)
			if not isPrivate or verbose:
				if isFunction:
					print(f"- {privateStr}<function> | {name}.{prop}()")
				else:
					print(f"- {privateStr}<property> | {name}.{prop} = {value}")
		except AttributeError:
			print(f"- {prop}: <unreadable>")
		except NameError:
			print(f"- {prop}: <name error>")
		except td.tdError:
			print(f"- {prop}: <tdError>")
			continue

	print(f"------- end inspection --------")
	print(f"===============================")
	return

def path_relative_to_project(path):
	isString = isinstance(path, str)
	if isString:
		return os.path.join(td.project.folder, path).replace("\\", "/") # os-independent option, and replaces backslashes with slashes for consistency
	else:
		path.insert(0, td.project.folder) # insert project folder at the beginning of the path array
		return os.path.join(*path).replace("\\", "/") # os-independent option, and replaces backslashes with slashes for consistency
		# return os.path.join(*pathArray) # os-independent option, but mixes slashes and backslashes
		# return "/".join(pathArray)