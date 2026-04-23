lines = []
with open("modal_user_message.py", "r", encoding="utf-8") as f:
    for line in f:
        # Ignore lines with 'try:' 'finally:' 'pass' at the start of blocks
        s = line.strip('\n')
        # Check if the line is exactly these tokens with spaces
        if s == "        try:": continue
        if s == "        finally:": continue
        if s == "            pass": continue
        if s == "    try:": continue
        if s == "    finally:": continue
        if s == "        pass": continue
        lines.append(line)

with open("modal_user_message.py", "w", encoding="utf-8") as f:
    f.writelines(lines)

import py_compile
try:
    py_compile.compile("modal_user_message.py", doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"Compilation Failed: {e}")
