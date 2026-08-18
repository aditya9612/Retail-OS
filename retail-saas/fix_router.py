from pathlib import Path
import re

path = Path("app/api/v1/stores/router.py")
text = path.read_text(encoding="utf-8")

text = re.sub(
    r'def assign_staff\(\s*'
    r'staff_id: int,\s*'
    r'store_id: int,\s*'
    r'db: Session = Depends\(get_db\),\s*'
    r'\):',
    '''def assign_staff(
    staff_id: int,
    store_id: int,
    user: User = Depends(
        require_permission("employees:write")
    ),
    db: Session = Depends(get_db),
):''',
    text,
    count=1
)

text = re.sub(
    r'def transfer_staff\(\s*'
    r'staff_id: int,\s*'
    r'store_id: int,\s*'
    r'db: Session = Depends\(get_db\),\s*'
    r'\):',
    '''def transfer_staff(
    staff_id: int,
    store_id: int,
    user: User = Depends(
        require_permission("employees:write")
    ),
    db: Session = Depends(get_db),
):''',
    text,
    count=1
)

text = re.sub(
    r'def list_all_staff\(\s*'
    r'db: Session = Depends\(get_db\),\s*'
    r'\):',
    '''def list_all_staff(
    user: User = Depends(
        require_permission("employees:read")
    ),
    db: Session = Depends(get_db),
):''',
    text,
    count=1
)

path.write_text(text, encoding="utf-8")

print("router.py saved successfully")
