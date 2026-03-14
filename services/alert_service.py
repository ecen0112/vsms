from database.db import get_db
from datetime import date, timedelta

def generate_alerts():
    """Generate and store alerts for low stock and expiring products."""
    conn = get_db()
    today = date.today()
    warn_date = today + timedelta(days=30)

    # Clear old unread alerts
    conn.execute("DELETE FROM alerts WHERE is_read=0")

    # Low stock alerts
    low_stock = conn.execute("""
        SELECT product_id, product_name, stock, low_stock_threshold
        FROM products WHERE stock <= low_stock_threshold AND is_active=1
    """).fetchall()
    for p in low_stock:
        conn.execute("""INSERT INTO alerts (alert_type, product_id, message)
            VALUES ('low_stock', ?, ?)""",
            (p['product_id'], f"Low stock: {p['product_name']} has only {p['stock']} {' units'} left"))

    # Expiring within 30 days
    expiring = conn.execute("""
        SELECT pb.batch_id, pb.product_id, p.product_name, pb.batch_number, pb.expiration_date,
               pb.remaining_quantity
        FROM product_batches pb
        JOIN products p ON pb.product_id = p.product_id
        WHERE pb.expiration_date IS NOT NULL
          AND pb.expiration_date > ? AND pb.expiration_date <= ?
          AND pb.remaining_quantity > 0
    """, (today.isoformat(), warn_date.isoformat())).fetchall()
    for b in expiring:
        conn.execute("""INSERT INTO alerts (alert_type, product_id, batch_id, message)
            VALUES ('expiring', ?, ?, ?)""",
            (b['product_id'], b['batch_id'],
             f"Expiring soon: {b['product_name']} (Batch {b['batch_number']}) expires on {b['expiration_date']}"))

    # Already expired
    expired = conn.execute("""
        SELECT pb.batch_id, pb.product_id, p.product_name, pb.batch_number, pb.expiration_date,
               pb.remaining_quantity
        FROM product_batches pb
        JOIN products p ON pb.product_id = p.product_id
        WHERE pb.expiration_date IS NOT NULL
          AND pb.expiration_date < ?
          AND pb.remaining_quantity > 0
    """, (today.isoformat(),)).fetchall()
    for b in expired:
        conn.execute("""INSERT INTO alerts (alert_type, product_id, batch_id, message)
            VALUES ('expired', ?, ?, ?)""",
            (b['product_id'], b['batch_id'],
             f"EXPIRED: {b['product_name']} (Batch {b['batch_number']}) expired on {b['expiration_date']}"))

    conn.commit()
    conn.close()

def get_alert_counts():
    conn = get_db()
    counts = {
        'low_stock': conn.execute("SELECT COUNT(*) FROM alerts WHERE alert_type='low_stock' AND is_read=0").fetchone()[0],
        'expiring': conn.execute("SELECT COUNT(*) FROM alerts WHERE alert_type='expiring' AND is_read=0").fetchone()[0],
        'expired': conn.execute("SELECT COUNT(*) FROM alerts WHERE alert_type='expired' AND is_read=0").fetchone()[0],
    }
    counts['total'] = counts['low_stock'] + counts['expiring'] + counts['expired']
    conn.close()
    return counts
