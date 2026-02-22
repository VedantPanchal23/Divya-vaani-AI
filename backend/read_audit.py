import sys

# Read the UTF-16LE file produced by PowerShell redirect
try:
    with open('audit_results.txt', 'r', encoding='utf-16-le', errors='replace') as f:
        content = f.read()
except:
    with open('audit_results.txt', 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

# Write as UTF-8
with open('audit_clean.txt', 'w', encoding='utf-8', errors='replace') as out:
    for line in content.split('\n'):
        clean = line.strip()
        if clean:
            out.write(clean + '\n')

print("Done")
