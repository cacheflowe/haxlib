# Python String Formatting

Learn essential string formatting techniques in Python, including interpolation, padding, and number formatting. These patterns are useful for creating formatted output, generating filenames, displaying data, and formatting numerical values.

## Overview

Python offers multiple ways to format strings, with f-strings being the most modern and readable approach. This guide covers common formatting patterns you'll use frequently.

## String Interpolation

Basic techniques for inserting variables into strings:

```python
# quick string interpolation
f'var = {variable}'
'var = {}'.format(variable) # alt
```

## Zero Padding Numbers

Add leading zeros to numbers for fixed-width formatting:

```python
# zero padding a number
'{:03d}'.format(1) # 001
'{:010d}'.format(9223) # 0000009223
```

## Zero Padding Strings

Pad strings with leading zeros:

```python
# zero pad a string
'hi'.zfill(10) # 0000000hi
'hi'.rjust(10, '0') # 0000000hi
```

## Rounding Numbers

Control decimal precision in formatted output:

```python
# rounding numbers
f'{variable:.2f}' # 2 decimal places
f'{variable:.0f}' # no decimal places
```

## Rounding with Padding

Combine padding and decimal precision for aligned numerical output:

```python
# rounding with padding
f'{variable:05.2f}' # 5 total spaces, 2 decimal places
```

## Thousand Separators

Format large numbers with separators for readability:

```python
# thousand separators
f'{1234567:,}' # 1,234,567
f'{1234567:_.2f}' # 1_234_567.00 (underscore separator)
```

## Percentage Formatting

Display values as percentages:

```python
# percentage formatting
f'{0.123:.1%}' # 12.3%
f'{0.5:.0%}' # 50%
```

## String Alignment

Align text within a fixed width using left, right, or center alignment:

```python
# string alignment
f'{text:<10}' # left align, 10 chars wide
f'{text:>10}' # right align, 10 chars wide
f'{text:^10}' # center align, 10 chars wide
```

## Hex and Binary Formatting

Format numbers in hexadecimal or binary notation:

```python
# hex/binary formatting
f'{255:02x}' # ff (hex, lowercase)
f'{255:02X}' # FF (hex, uppercase)
f'{8:08b}' # 00001000 (binary)
```

## String Truncation

Limit string length to a maximum number of characters:

```python
# string truncation
f'{long_text:.10}' # first 10 characters only
```

## Sign Formatting

Explicitly display positive and negative signs:

```python
# sign formatting
f'{value:+.2f}' # always show sign: +3.14 or -3.14
```
