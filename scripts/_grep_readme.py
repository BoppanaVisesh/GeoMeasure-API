import sys
patterns = ['TODO', 'your-', 'example.com', 'placeholder', '<your']
text = open('README.md', encoding='utf-8').read()
found = False
for p in patterns:
    matches = [(i+1, line.strip()) for i, line in enumerate(text.splitlines()) if p.lower() in line.lower()]
    if matches:
        print(f'FOUND "{p}": {matches}')
        found = True
if not found:
    print('CLEAN: no TODO / your- / example.com / placeholder / <your found in README.md')
