cat > prices.py <<'PY'
def apply_discount(price, percent):
    return price - price * percent / 100
PY
cat > test_prices.py <<'PY'
from prices import apply_discount


def test_ten_percent():
    assert apply_discount(200, 10) == 180
PY
