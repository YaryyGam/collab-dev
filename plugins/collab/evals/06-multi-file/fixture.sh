cat > api.py <<'PY'
import re


def register(payload):
    email = payload.get("email", "").strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", email):
        raise ValueError("invalid email")
    return {"email": email.lower()}
PY
cat > cli.py <<'PY'
import re
import sys


def main(argv):
    email = argv[1]
    if "@" not in email or not re.search(r"\.\w+$", email):
        print("invalid email")
        return 1
    print("ok", email)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PY
