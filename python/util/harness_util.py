import threading
from subprocess import Popen, PIPE, STDOUT

# Named, reusable prompts for run_named_prompt(). Add new entries here rather than
# hardcoding prompt strings at call sites, so the library stays the single source of truth.
PROMPTS = {
	'fix_network_errors': (
		"Can you use the td-docs-mcp mcp server and the td_http_api.py tools, along with "
		"the td-http-api.md skill to solve the error in the network that I'm currently "
		"looking at in the touchdesigner UI?"
	),
}


def run_pi_agent(prompt: str) -> threading.Thread:
	"""Run a one-shot `pi` CLI session (a locally-hosted LLM agent) in a background thread,
	streaming its output to the Textport as it arrives. Non-blocking — returns immediately,
	so it's safe to call from the main thread (e.g. the Textport) without freezing TD.
	See .ai/skills/td-http-api.md 'Invoking an agent from the shell' for context."""
	def _run():
		p = Popen(
			['pi', '-p', prompt],
			stdout=PIPE, stderr=STDOUT, text=True, bufsize=1
		)
		for line in p.stdout:
			print(line, end='')
		p.stdout.close()
		p.wait()

	thread = threading.Thread(target=_run)
	thread.daemon = True
	thread.start()
	return thread


def run_named_prompt(name: str) -> threading.Thread:
	"""Run a prompt from the PROMPTS library by name. Raises ValueError with the available
	names if 'name' isn't in the library — fail loud rather than silently running nothing."""
	if name not in PROMPTS:
		raise ValueError(f"unknown prompt '{name}'. Available: {sorted(PROMPTS)}")
	return run_pi_agent(PROMPTS[name])
