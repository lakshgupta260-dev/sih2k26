import re

with open('backend/app/services/reporting.py', 'r', encoding='utf-8') as f:
    code = f.read()

new_status_of = '''        def _status_of(activity: Activity) -> str:
            r = rollup_map.get(activity.id)
            if not r:
                return ActivityStatus.NOT_STARTED
            if not r.is_leaf:
                if r.completion_percentage >= 100.0:
                    return ActivityStatus.COMPLETED
                if r.completion_percentage > 0.0:
                    return ActivityStatus.IN_PROGRESS
                return ActivityStatus.NOT_STARTED
            return r.status'''

code = re.sub(r'        def _status_of\(activity: Activity\) -> str:\n            r = rollup_map\.get\(activity\.id\)\n            return r\.status if r else ActivityStatus\.NOT_STARTED', new_status_of, code)

with open('backend/app/services/reporting.py', 'w', encoding='utf-8') as f:
    f.write(code)
