from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database.db import get_db
from services.alert_service import generate_alerts, get_alert_counts
from functools import wraps
from werkzeug.security import generate_password_hash

alert_bp = Blueprint('alerts', __name__)
user_bp = Blueprint('users', __name__)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated

# --- Alert Routes ---
@alert_bp.route('/alerts')
@login_required
def index():
    generate_alerts()
    conn = get_db()
    alerts = conn.execute("""
        SELECT a.*, p.product_name FROM alerts a
        LEFT JOIN products p ON a.product_id=p.product_id
        ORDER BY a.is_read ASC, a.created_at DESC
    """).fetchall()
    counts = get_alert_counts()
    conn.close()
    return render_template('alerts.html', alerts=alerts, counts=counts)

@alert_bp.route('/api/alerts/mark-read/<int:aid>', methods=['POST'])
@login_required
def mark_read(aid):
    conn = get_db()
    conn.execute("UPDATE alerts SET is_read=1 WHERE alert_id=?", (aid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@alert_bp.route('/api/alerts/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    conn = get_db()
    conn.execute("UPDATE alerts SET is_read=1")
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@alert_bp.route('/api/alerts/count')
@login_required
def count():
    return jsonify(get_alert_counts())

# --- User Management Routes ---
@user_bp.route('/users')
@login_required
@admin_required
def index():
    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY role, full_name").fetchall()
    conn.close()
    return render_template('users.html', users=users)

@user_bp.route('/users/add', methods=['POST'])
@login_required
@admin_required
def add():
    data = request.form
    conn = get_db()
    try:
        conn.execute("""INSERT INTO users (username, password, full_name, role, email, phone)
                        VALUES (?,?,?,?,?,?)""",
                     (data['username'], generate_password_hash(data['password']),
                      data['full_name'], data['role'], data.get('email',''), data.get('phone','')))
        conn.commit()
        flash('User added successfully!', 'success')
    except Exception as e:
        flash(f'Error: Username may already exist. {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('users.index'))

@user_bp.route('/users/<int:uid>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle(uid):
    conn = get_db()
    user = conn.execute("SELECT is_active FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.execute("UPDATE users SET is_active=? WHERE user_id=?", (0 if user['is_active'] else 1, uid))
    conn.commit()
    conn.close()
    flash('User status updated.', 'success')
    return redirect(url_for('users.index'))

@user_bp.route('/users/<int:uid>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_password(uid):
    new_pw = request.form.get('new_password', '')
    if len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('users.index'))
    conn = get_db()
    conn.execute("UPDATE users SET password=? WHERE user_id=?", (generate_password_hash(new_pw), uid))
    conn.commit()
    conn.close()
    flash('Password reset successfully.', 'success')
    return redirect(url_for('users.index'))
