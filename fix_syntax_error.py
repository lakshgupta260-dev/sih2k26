import re

with open('frontend/src/pages/project/Reports.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace('TrendingUp,\\n  Trash2,', 'TrendingUp,\n  Trash2,')

with open('frontend/src/pages/project/Reports.tsx', 'w', encoding='utf-8') as f:
    f.write(code)
