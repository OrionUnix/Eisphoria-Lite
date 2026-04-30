import sys
import os

print(f"PYTHONPATH: {sys.path}")
print(f"CWD: {os.getcwd()}")

try:
    import core.extractor as extractor
    print(f"SUCCESS: core.extractor loaded from {extractor.__file__}")
    
    # Check for the problematic line
    with open(extractor.__file__, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if 'InMemoryUploadedFile' in line:
                print(f"FOUND problematic string at line {i+1}: {line.strip()}")
except Exception as e:
    print(f"ERROR: Could not load core.extractor: {e}")

try:
    import core.calculator as calculator
    print(f"SUCCESS: core.calculator loaded from {calculator.__file__}")
except Exception as e:
    print(f"ERROR: Could not load core.calculator: {e}")
