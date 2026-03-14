from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from database.db import get_db
from functools import wraps
from datetime import date, timedelta

report_bp = Blueprint('reports', __name__)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

@report_bp.route('/reports')
@login_required
def index():
    conn = get_db()
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    year_start = today.replace(month=1, day=1).isoformat()

    summary = {
        'today_revenue': conn.execute("""SELECT COALESCE(SUM(total_amount),0) FROM transactions 
            WHERE DATE(created_at)=? AND status='completed'""", (today.isoformat(),)).fetchone()[0],
        'monthly_revenue': conn.execute("""SELECT COALESCE(SUM(total_amount),0) FROM transactions 
            WHERE DATE(created_at)>=? AND status='completed'""", (month_start,)).fetchone()[0],
        'yearly_revenue': conn.execute("""SELECT COALESCE(SUM(total_amount),0) FROM transactions 
            WHERE DATE(created_at)>=? AND status='completed'""", (year_start,)).fetchone()[0],
        'total_transactions': conn.execute("""SELECT COUNT(*) FROM transactions WHERE status='completed'""").fetchone()[0],
        'monthly_profit': conn.execute("""
            SELECT COALESCE(SUM(ti.total_price - (ti.quantity * p.cost_price)),0)
            FROM transaction_items ti
            JOIN transactions t ON ti.transaction_id=t.transaction_id
            JOIN products p ON ti.product_id=p.product_id
            WHERE DATE(t.created_at)>=? AND t.status='completed'""", (month_start,)).fetchone()[0],
    }

    # Top 10 best sellers
    best_sellers = conn.execute("""
        SELECT p.product_name, p.category, p.unit,
               SUM(ti.quantity) as total_sold,
               SUM(ti.total_price) as revenue,
               SUM(ti.total_price - (ti.quantity * p.cost_price)) as profit
        FROM transaction_items ti
        JOIN products p ON ti.product_id=p.product_id
        JOIN transactions t ON ti.transaction_id=t.transaction_id
        WHERE t.status='completed'
        GROUP BY p.product_id ORDER BY total_sold DESC LIMIT 10
    """).fetchall()

    # Monthly breakdown (last 12 months)
    monthly_data = []
    for i in range(11, -1, -1):
        d = today.replace(day=1) - timedelta(days=i*30)
        m_start = d.replace(day=1).isoformat()
        if d.month == 12:
            m_end = d.replace(year=d.year+1, month=1, day=1) - timedelta(days=1)
        else:
            m_end = d.replace(month=d.month+1, day=1) - timedelta(days=1)
        m_end = m_end.isoformat()
        row = conn.execute("""
            SELECT COALESCE(SUM(total_amount),0) as revenue, COUNT(*) as txn_count
            FROM transactions WHERE DATE(created_at) BETWEEN ? AND ? AND status='completed'
        """, (m_start, m_end)).fetchone()
        monthly_data.append({
            'month': d.strftime('%b %Y'),
            'revenue': round(row['revenue'], 2),
            'count': row['txn_count']
        })

    # Category sales
    category_sales = conn.execute("""
        SELECT p.category, SUM(ti.total_price) as revenue, SUM(ti.quantity) as units_sold
        FROM transaction_items ti
        JOIN products p ON ti.product_id=p.product_id
        JOIN transactions t ON ti.transaction_id=t.transaction_id
        WHERE t.status='completed'
        GROUP BY p.category ORDER BY revenue DESC
    """).fetchall()

    # Daily sales (last 30 days)
    daily_data = []
    for i in range(29, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        amt = conn.execute("""SELECT COALESCE(SUM(total_amount),0) FROM transactions 
            WHERE DATE(created_at)=? AND status='completed'""", (d,)).fetchone()[0]
        daily_data.append({'date': d[5:], 'amount': round(amt, 2)})

    conn.close()
    return render_template('reports.html',
        summary=summary, best_sellers=best_sellers,
        monthly_data=monthly_data, category_sales=category_sales, daily_data=daily_data)

@report_bp.route('/api/reports/audit-log')
@login_required
def audit_log():
    conn = get_db()
    page = int(request.args.get('page', 1))
    per_page = 30
    offset = (page - 1) * per_page
    logs = conn.execute("""
        SELECT al.*, u.full_name as user_name
        FROM audit_logs al LEFT JOIN users u ON al.user_id=u.user_id
        ORDER BY al.created_at DESC LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    conn.close()
    return jsonify({'logs': [dict(l) for l in logs], 'total': total})
