@REM Epson Thermal Printer Command Script
@REM This script activates the TD virtual environment and runs the Epson Thermal Print Python script with specified arguments.

@REM Activate TD virtual environment on command line
@REM ..\..\..\haxlib_vEnv\Scripts\activate.bat
..\haxlib_vEnv\Scripts\Activate.ps1

@REM Run the Python script with arguments
python ..\tox\haxlib\hardware\EpsonThermalPrint.py --ip 192.168.1.226 --file ./readme.md --markdown
