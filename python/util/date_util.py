
def format_seconds(seconds, show_hours=False, ms_digits=0):
	hours = seconds // 3600
	remaining_seconds = seconds % 3600
	minutes = remaining_seconds // 60
	remaining_seconds = remaining_seconds % 60
	str_hours = f"{int(hours):02d}:" if show_hours else ""
	str_minutes = f"{int(minutes):02d}:"
	str_seconds = f"{int(remaining_seconds):02d}"
	str_ms = f".{int((seconds - int(seconds)) * 10**ms_digits):0{ms_digits}d}" if ms_digits > 0 else ""
	return f"{str_hours}{str_minutes}{str_seconds}{str_ms if ms_digits > 0 else ''}"