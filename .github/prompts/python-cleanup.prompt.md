# Python Code Cleanup

Clean up and polish the selected Python code following TouchDesigner Python conventions.

## Reference

Use the guidelines defined in [SKILL.md](../skills/td-python/SKILL.md) for all conventions.

## Cleanup Tasks

### 1. Add Type Hints
- Add type hints to all function parameters and return types
- Use `Optional[T]` for nullable types
- Use `Union[T1, T2]` for multiple possible types
- Common TD types: `OP`, `COMP`, `DAT`, `TOP`, `CHOP`, `SOP`, `MAT`, `baseCOMP`
  - Please use specific sub-types when possible (e.g. `tableDAT` instead of `DAT`)

### 2. Fix Naming Conventions
- **Classes**: `PascalCase`
- **Extension Methods (public)** (public methods on extension classes): `PascalCase`
- **Extension Methods (private)** (private methods on extension classes): `camelCase`
- **Utility Functions** (standalone helper .py files): `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private Methods**: : `camelCase`, no leading underscore
- **AppStoreToggle Callbacks**: `On_functionName` - these are public methods called dynamically on python extensions by internal tooling and should not be changed. Callback functions include:
```python
		def On_show(self):
		def On_hide(self):
		def On_will_show(self):
		def On_showing(self):
		def On_will_hide(self):
		def On_hidden(self):
```

### 3. Add Documentation
- Add docstrings to all classes and public methods, unless the function is small and self-documenting with a descriptive name
- Use Google-style docstring format with Args/Returns sections for complex functions
- Keep docstrings concise but descriptive

### 4. Logging Format
- Use bracketed class/module prefix: `print(f"[ClassName] message")`
- Use f-strings for all string formatting

### 5. Code Quality
- Replace bare `except:` with specific exception types
- Cache repeated `op()` or `ops()` calls into variables
- Replace magic strings with constants
- Use `is not None` instead of `!= None`
- Remove unnecessary `return` statements at end of functions
- Remove redundant comments that just repeat the code

### 6. Formatting
- Use **tabs** for indentation (TouchDesigner convention)
- Add blank lines between method definitions
- Group related methods with section comment headers:
```python
###################################################
# Section Name
###################################################
```

## Output

Return the cleaned code with all improvements applied. Preserve the original logic and functionality.
