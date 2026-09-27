with open('backend/app/services/progress.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'status=progress.status if progress else ActivityStatus.NOT_STARTED,' in line:
        lines[i] = '''                    status=(
                        ActivityStatus.COMPLETED if (earned / weight * 100.0) >= 100.0 else
                        ActivityStatus.IN_PROGRESS if (earned / weight * 100.0) > 0.0 else
                        ActivityStatus.NOT_STARTED
                    ) if children.get(node_id) else (progress.status if progress else ActivityStatus.NOT_STARTED),
'''

with open('backend/app/services/progress.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
