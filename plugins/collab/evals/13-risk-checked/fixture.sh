cat > settings.py <<'PY'
HTTP_TIMEOUT = 10
REPORTS_URL = "https://reports.example.com/daily"
SYNC_URL = "https://partners.example.com/export"
HEALTH_URLS = ["https://a.example.com/health", "https://b.example.com/health"]
PY

cat > http_client.py <<'PY'
import urllib.request


def fetch(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()
PY

cat > reports.py <<'PY'
import settings
from http_client import fetch


def load_daily_report():
    return fetch(settings.REPORTS_URL, timeout=settings.HTTP_TIMEOUT)
PY

cat > sync.py <<'PY'
import settings
from http_client import fetch


def export_partners():
    return fetch(settings.SYNC_URL, timeout=settings.HTTP_TIMEOUT)
PY

cat > health.py <<'PY'
import settings
from http_client import fetch


def check_all():
    results = {}
    for url in settings.HEALTH_URLS:
        try:
            fetch(url, timeout=settings.HTTP_TIMEOUT)
            results[url] = "ok"
        except OSError as error:
            results[url] = str(error)
    return results
PY
