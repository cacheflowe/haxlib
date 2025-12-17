import os
import td

def create_temp_path():
    if not os.path.exists(temp_path()):
        os.makedirs(temp_path())

def temp_path():
    return td.project.folder + '/tmp'

def delete_file(filePath):
    if os.path.exists(filePath):
        os.remove(filePath)

def open_folder(path):
    os.startfile(path)
