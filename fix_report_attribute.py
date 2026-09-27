import re

with open('backend/app/services/reporting.py', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace('return float(r.percent_complete) if r else 0.0', 'return float(r.completion_percentage) if r else 0.0')

with open('backend/app/services/reporting.py', 'w', encoding='utf-8') as f:
    f.write(code)
