cat > orders.py <<'PY'
def process_orders(orders, discounts, tax_rate):
    result = []
    for o in orders:
        if o.get("status") == "cancelled":
            continue
        total = 0
        for item in o["items"]:
            price = item["price"] * item["qty"]
            if item["sku"] in discounts:
                price = price * (1 - discounts[item["sku"]])
            total += price
        if total > 1000:
            total = total * 0.95
        total = total * (1 + tax_rate)
        result.append({"id": o["id"], "total": round(total, 2)})
    return result
PY
