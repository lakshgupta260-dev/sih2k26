import re

with open('backend/app/services/reporting.py', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace('from app.services.progress import ProgressService', '        from app.services.progress import ProgressService')

with open('backend/app/services/reporting.py', 'w', encoding='utf-8') as f:
    f.write(code)
