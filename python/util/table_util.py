import json
import td

def get_kv_prop(table: td.DAT, key):
	row = table.row(key)
	if row != None:
		return row[1]
	else:
		return None

def set_kv_prop(table: td.DAT, key, value):
	row = table.row(key)
	if row != None:
		table.replaceRow(key, [key, value])
	else:
		if table.numRows == 0:
			table.appendRow([key, value])
		else:
			table.appendRow([key, value], table.numRows - 1)

def remove_kv_prop(table: td.DAT, key):
	if table.row(key) != None:
		table.deleteRow(key)

def remove_all_rows(table: td.DAT):
	table.clear()

def table_to_json(table: td.DAT):
	data = {}
	for row in range(0, table.numRows):
		# get data from table
		key = table[row, 0].val
		value = table[row, 1].val

		# check/convert datatypes for py -> json types
		if len(value) == 0:
			value = None
		elif value.isnumeric():
			value = float(value)
		elif value.lower() == 'true':
				value = True
		elif value.lower() == 'false':
				value = False	

		# set data on outgoing json object
		data[key] = value
	return data

def table_to_json_str(table: td.DAT):
	return json.dumps(table_to_json(table))