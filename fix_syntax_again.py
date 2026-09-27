with open('frontend/src/api/generatedReports.ts', 'r', encoding='utf-8') as f:
    code = f.read()

import re
code = re.sub(r'apiClient\.delete\(.*\)\.then\(\(r\) => r\.data\),', 'apiClient.delete(/projects//generated-reports/).then((r) => r.data),', code)

with open('frontend/src/api/generatedReports.ts', 'w', encoding='utf-8') as f:
    f.write(code)
