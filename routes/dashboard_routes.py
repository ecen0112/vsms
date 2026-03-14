from flask import Blueprint, render_template, jsonify, session, redirect, url_for
from database.db import get_db
from services.alert_service import generate_alerts, get_alert_counts
from datetime import date, timedelta
from functools import wraps

dashboard_bp = Blueprint('dashboard', __name__)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

@dashboard_bp.route('/dashboard')
@login_required
def index():
    generate_alerts()
    conn = get_db()
    today = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()

    stats = {
        'total_products': conn.execute("SELECT COUNT(*) FROM products WHERE is_active=1").fetchone()[0],
        'low_stock': conn.execute("""SELECT COUNT(*) FROM products 
            WHERE stock <= low_stock_threshold AND is_active=1""").fetchone()[0],
        'expiring_soon': conn.execute("""SELECT COUNT(*) FROM product_batches 
            WHERE expiration_date IS NOT NULL 
            AND expiration_date BETWEEN ? AND ?
            AND remaining_quantity > 0""",
            (today, (date.today() + timedelta(days=30)).isoformat())).fetchone()[0],
        'today_sales': conn.execute("""SELECT COALESCE(SUM(total_amount),0) FROM transactions 
            WHERE DATE(created_at)=? AND status='completed'""", (today,)).fetchone()[0],
        'today_transactions': conn.execute("""SELECT COUNT(*) FROM transactions 
            WHERE DATE(created_at)=? AND status='completed'""", (today,)).fetchone()[0],
        'monthly_sales': conn.execute("""SELECT COALESCE(SUM(total_amount),0) FROM transactions 
            WHERE DATE(created_at)>=? AND status='completed'""", (month_start,)).fetchone()[0],
        'inventory_value': conn.execute("""SELECT COALESCE(SUM(stock * cost_price),0) 
            FROM products WHERE is_active=1""").fetchone()[0],
        'total_suppliers': conn.execute("SELECT COUNT(*) FROM suppliers WHERE is_active=1").fetchone()[0],
    }

    # Best selling products (top 5)
    best_sellers = conn.execute("""
        SELECT p.product_name, SUM(ti.quantity) as total_sold, SUM(ti.total_price) as revenue
        FROM transaction_items ti
        JOIN products p ON ti.product_id = p.product_id
        JOIN transactions t ON ti.transaction_id = t.transaction_id
        WHERE t.status = 'completed'
        GROUP BY p.product_id
        ORDER BY total_sold DESC LIMIT 5
    """).fetchall()

    # Last 7 days sales
    daily_sales = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        amt = conn.execute("""SELECT COALESCE(SUM(total_amount),0) FROM transactions 
            WHERE DATE(created_at)=? AND status='completed'""", (d,)).fetchone()[0]
        daily_sales.append({'date': d, 'amount': amt})

    # Category distribution
    categories = conn.execute("""
        SELECT category, COUNT(*) as count, SUM(stock * price) as value
        FROM products WHERE is_active=1 GROUP BY category
    """).fetchall()

    # Recent transactions
    recent_txns = conn.execute("""
        SELECT t.*, u.full_name as cashier_name
        FROM transactions t JOIN users u ON t.cashier_id = u.user_id
        WHERE t.status='completed'
        ORDER BY t.created_at DESC LIMIT 8
    """).fetchall()

    # Low stock items
    low_stock_items = conn.execute("""
        SELECT product_name, stock, low_stock_threshold, unit, category
        FROM products WHERE stock <= low_stock_threshold AND is_active=1
        ORDER BY stock ASC LIMIT 8
    """).fetchall()

    alert_counts = get_alert_counts()
    conn.close()

    return render_template('dashboard.html',
        stats=stats,
        best_sellers=best_sellers,
        daily_sales=daily_sales,
        categories=categories,
        recent_txns=recent_txns,
        low_stock_items=low_stock_items,
        alert_counts=alert_counts
    )

@dashboard_bp.route('/api/dashboard/chart-data')
@login_required
def chart_data():
    conn = get_db()
    # Last 30 days
    labels, values = [], []
    for i in range(29, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        amt = conn.execute("""SELECT COALESCE(SUM(total_amount),0) FROM transactions 
            WHERE DATE(created_at)=? AND status='completed'""", (d,)).fetchone()[0]
        labels.append(d[5:])  # MM-DD
        values.append(round(amt, 2))
    conn.close()
    return jsonify({'labels': labels, 'values': values})
