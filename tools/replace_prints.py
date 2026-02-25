#!/usr/bin/env python3
"""One-time script to replace print() with logger calls in main.py.
Run once then delete this file."""

import re

filepath = r'c:\Users\jstol\eclipse-workspace\AvareonWar\main.py'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
new_lines = []

for i, line in enumerate(lines):
    # Skip lines that don't contain print( or are comments
    stripped = line.lstrip()
    if not stripped.startswith('print(') and 'print(' not in stripped:
        new_lines.append(line)
        continue

    # Skip if it's in a comment
    code_before_hash = line.split('#')[0]
    if 'print(' not in code_before_hash:
        new_lines.append(line)
        continue

    # Skip if print is part of a variable name (e.g., blueprint)
    # Check that 'print(' is preceded by non-alphanumeric or is at start
    idx = code_before_hash.find('print(')
    if idx > 0 and code_before_hash[idx-1].isalpha():
        new_lines.append(line)
        continue

    # Determine log level based on content
    line_lower = line.lower()

    # Determine the indent
    indent = line[:len(line) - len(line.lstrip())]

    # Extract the print content
    # Match print(f"..." or print("...")
    match = re.match(r'^(\s*)print\((.*)\)\s*$', line)
    if not match:
        # Multi-line print or complex expression - leave as-is for manual review
        new_lines.append(line)
        continue

    indent = match.group(1)
    content_str = match.group(2)

    # Determine log level
    if any(kw in line_lower for kw in ['error', 'failed', 'cannot', "can't"]):
        if 'warning' in line_lower or 'warn' in line_lower:
            level = 'warning'
        else:
            level = 'error'
    elif any(kw in line_lower for kw in ['warning', 'warn']):
        level = 'warning'
    elif any(kw in line_lower for kw in ['[debug]', 'debug']):
        level = 'debug'
    elif any(kw in line_lower for kw in ['rejected', 'desync', 'mismatch']):
        level = 'warning'
    else:
        level = 'info'

    # Special overrides:
    # Network debug messages should be debug level
    if '[network]' in line_lower and 'sync:' in line_lower:
        level = 'debug'
    if '[network]' in line_lower and ('received' in line_lower or 'sent' in line_lower):
        level = 'debug'
    if '[sim]' in line_lower and ('queued' in line_lower or 'converted' in line_lower or 'removed' in line_lower):
        level = 'debug'

    # Remove redundant prefix tags from the content since the logger adds module name
    # But keep [NETWORK], [SIM], etc. as they provide context

    new_line = f'{indent}logger.{level}({content_str})'
    new_lines.append(new_line)

result = '\n'.join(new_lines)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(result)

print(f"Done! Processed {len(lines)} lines.")
