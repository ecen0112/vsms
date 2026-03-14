from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from database.db import get_db
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

def log_audit(user_id, action, module, description, ip=None):
    try:
        conn = get_db()
        conn.execute("""INSERT INTO audit_logs (user_id, action, module, description, ip_address)
                        VALUES (?, ?, ?, ?, ?)""", (user_id, action, module, description, ip))
        conn.commit()
        conn.close()
    except:
        pass

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND is_active=1", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            conn = get_db()
            conn.execute("UPDATE users SET last_login=? WHERE user_id=?",
                         (datetime.now().isoformat(), user['user_id']))
            conn.commit()
            conn.close()
            log_audit(user['user_id'], 'LOGIN', 'Authentication',
                      f"User '{username}' logged in", request.remote_addr)
            flash(f'Welcome back, {user["full_name"]}!', 'success')
            return redirect(url_for('dashboard.index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    if 'user_id' in session:
        log_audit(session['user_id'], 'LOGOUT', 'Authentication',
                  f"User '{session.get('username')}' logged out", request.remote_addr)
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
