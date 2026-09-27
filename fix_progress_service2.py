with open('backend/app/services/progress.py', 'r', encoding='utf-8') as f:
    code = f.read()

target = '''                      completion_percentage=(earned / weight * 100.0) if weight > 0 else 0.0,
                      status=progress.status if progress else ActivityStatus.NOT_STARTED,'''

replacement = '''                      completion_percentage=(earned / weight * 100.0) if weight > 0 else 0.0,
                      status=(
                          ActivityStatus.COMPLETED if (earned / weight * 100.0) >= 100.0 else
                          ActivityStatus.IN_PROGRESS if (earned / weight * 100.0) > 0.0 else
                          ActivityStatus.NOT_STARTED
                      ) if children.get(node_id) else (progress.status if progress else ActivityStatus.NOT_STARTED),'''

code = code.replace(target, replacement)

with open('backend/app/services/progress.py', 'w', encoding='utf-8') as f:
    f.write(code)
