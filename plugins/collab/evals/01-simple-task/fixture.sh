cat > users.py <<'PY'
def get_usr(user_id, users):
    for u in users:
        if u["id"] == user_id:
            return u
    return None
PY
cat > app.py <<'PY'
from users import get_usr

def show(user_id, users):
    return get_usr(user_id, users)
PY
