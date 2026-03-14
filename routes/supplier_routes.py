from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database.db import get_db
from functools import wraps

supplier_bp = Blueprint('suppliers', __name__)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get('role') not in roles:
                flash('Access denied.', 'danger')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

@supplier_bp.route('/suppliers')
@login_required
def index():
    conn = get_db()
    suppliers = conn.execute("""
        SELECT s.*, COUNT(p.product_id) as product_count
        FROM suppliers s LEFT JOIN products p ON s.supplier_id=p.supplier_id AND p.is_active=1
        WHERE s.is_active=1 GROUP BY s.supplier_id ORDER BY s.name
    """).fetchall()
    conn.close()
    return render_template('suppliers.html', suppliers=suppliers)

@supplier_bp.route('/suppliers/add', methods=['POST'])
@login_required
@role_required('admin', 'inventory_manager')
def add():
    data = request.form
    conn = get_db()
    conn.execute("""INSERT INTO suppliers (name, contact_person, phone, email, address, notes)
                    VALUES (?,?,?,?,?,?)""",
                 (data['name'], data.get('contact_person',''), data.get('phone',''),
                  data.get('email',''), data.get('address',''), data.get('notes','')))
    conn.commit()
    conn.close()
    flash('Supplier added successfully!', 'success')
    return redirect(url_for('suppliers.index'))

@supplier_bp.route('/suppliers/<int:sid>/edit', methods=['POST'])
@login_required
@role_required('admin', 'inventory_manager')
def edit(sid):
    data = request.form
    conn = get_db()
    conn.execute("""UPDATE suppliers SET name=?, contact_person=?, phone=?, email=?, address=?, notes=?
                    WHERE supplier_id=?""",
                 (data['name'], data.get('contact_person',''), data.get('phone',''),
                  data.get('email',''), data.get('address',''), data.get('notes',''), sid))
    conn.commit()
    conn.close()
    flash('Supplier updated!', 'success')
    return redirect(url_for('suppliers.index'))

@supplier_bp.route('/suppliers/<int:sid>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(sid):
    conn = get_db()
    conn.execute("UPDATE suppliers SET is_active=0 WHERE supplier_id=?", (sid,))
    conn.commit()
    conn.close()
    flash('Supplier removed.', 'success')
    return redirect(url_for('suppliers.index'))

@supplier_bp.route('/api/suppliers')
@login_required
def api_list():
    conn = get_db()
    suppliers = conn.execute("SELECT * FROM suppliers WHERE is_active=1 ORDER BY name").fetchall()
    conn.close()
    return jsonify({'suppliers': [dict(s) for s in suppliers]})
