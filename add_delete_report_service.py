import re

with open('backend/app/services/reporting.py', 'r', encoding='utf-8') as f:
    code = f.read()

injection = '''
    def delete_report(
        self, project_id: uuid.UUID, report_id: uuid.UUID, current_user: User
    ) -> None:
        project = self._ensure_access(project_id, current_user)
        report = self.db.execute(
            select(GeneratedReport).where(
                GeneratedReport.id == report_id,
                GeneratedReport.project_id == project.id,
            )
        ).scalar_one_or_none()
        if not report:
            raise NotFoundError("Report not found")
        self.db.delete(report)
        self.db.commit()
'''

code = code + '\n' + injection

with open('backend/app/services/reporting.py', 'w', encoding='utf-8') as f:
    f.write(code)
