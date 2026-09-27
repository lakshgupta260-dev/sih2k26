import re

with open('backend/app/api/v1/generated_reports.py', 'r', encoding='utf-8') as f:
    code = f.read()

injection = '''
@router.delete("/{report_id}")
def delete_generated_report(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    ReportService(db).delete_report(project_id, report_id, current_user)
'''

code = code + '\n' + injection

with open('backend/app/api/v1/generated_reports.py', 'w', encoding='utf-8') as f:
    f.write(code)
