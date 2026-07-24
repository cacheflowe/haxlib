import penner
import inspect

from typing import Any

_norm_fns = [name for name, obj in inspect.getmembers(penner, inspect.isfunction) if 'Norm' in name]

# press 'Setup Parameters' in the OP to call this function to re-create the
# parameters.
def onSetupParameters(scriptOp: scriptCHOP):
	page = scriptOp.appendCustomPage('Custom')
	p = page.appendMenu('Easingfunc', label='Easing Function')
	p[0].menuNames = _norm_fns
	p[0].menuLabels = _norm_fns
	return

def onCook(scriptOp: scriptCHOP):
	scriptOp.clear()
	chan = scriptOp.appendChan('chan1')
	inputVal = scriptOp.inputs[0][0][0]
	fn = getattr(penner, scriptOp.par.Easingfunc.eval())
	chan[0] = fn(inputVal)
	return

def onGetCookLevel(scriptOp: scriptCHOP) -> CookLevel:
	return CookLevel.AUTOMATIC
