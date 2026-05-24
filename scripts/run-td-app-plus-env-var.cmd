pushd ..
set sys_env_var=Hello from shell env var!
set TD_APP_PATH=C:\Program Files\Derivative\TouchDesigner\bin\TouchDesigner.exe
start "%TD_APP_PATH%" "haxlib.toe"
popd