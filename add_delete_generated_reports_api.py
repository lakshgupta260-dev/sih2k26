import re

with open('frontend/src/api/generatedReports.ts', 'r', encoding='utf-8') as f:
    code = f.read()

injection = '''
  delete: (projectId: string, reportId: string) =>
    apiClient.delete(/projects//generated-reports/).then((r) => r.data),
'''

code = code.replace('};', injection + '\n};')

with open('frontend/src/api/generatedReports.ts', 'w', encoding='utf-8') as f:
    f.write(code)
