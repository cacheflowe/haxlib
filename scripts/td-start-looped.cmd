:restart

echo make sure processes are killed before starting
taskkill /F /IM "touchdesigner.exe" > nul 2>&1

echo Starting app at %TIME%
start /WAIT "TD Launch" ..\haxlib.toe

echo Restarting app...
goto restart

exit