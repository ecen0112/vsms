from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database.db import get_db
from functools import wraps
from datetime import date, datetime
import random, string

pos_bp = Blueprint('pos', __name__)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def generate_txn_code():
    date_str = date.today().strftime('%Y%m%d')
    rand = ''.join(random.choices(string.digits + string.ascii_uppercase, k=5))
    return f"TXN-{date_str}-{rand}"

@pos_bp.route('/pos')
@login_required
def index():
    return render_template('pos.html')

@pos_bp.route('/api/pos/products-all')
@login_required
def products_all():
    """Returns ALL products in one shot – cached on the client for fast POS."""
    conn = get_db()
    products = conn.execute("""
        SELECT product_id, product_name, barcode, category, brand,
               price, cost_price, stock, unit, requires_prescription,
               low_stock_threshold, image
        FROM products WHERE is_active=1
        ORDER BY category, product_name
    """).fetchall()
    conn.close()
    return jsonify({'products': [dict(p) for p in products]})

@pos_bp.route('/api/pos/checkout', methods=['POST'])
@login_required
def checkout():
    data = request.get_json()
    if not data or not data.get('items'):
        return jsonify({'success': False, 'message': 'Cart is empty'}), 400

    items           = data['items']
    customer_name   = (data.get('customer_name') or 'Walk-in Customer').strip()
    customer_phone  = (data.get('customer_phone') or '').strip()
    discount_pct    = max(0, min(100, float(data.get('discount_percent', 0))))
    payment_method  = data.get('payment_method', 'cash')
    amount_paid     = float(data.get('amount_paid', 0))
    notes           = data.get('notes', '')
    include_vat     = bool(data.get('include_vat', True))

    # Deduplicate items by product_id (sum quantities)
    merged = {}
    for it in items:
        pid = int(it['product_id'])
        if pid in merged:
            merged[pid]['quantity'] += int(it['quantity'])
        else:
            merged[pid] = {'product_id': pid, 'quantity': int(it['quantity']),
                           'price': float(it['price'])}
    items = list(merged.values())

    conn = get_db()
    try:
        # Lock products for this transaction
        subtotal = sum(i['price'] * i['quantity'] for i in items)
        discount_amount = round(subtotal * (discount_pct / 100), 4)
        after_discount  = subtotal - discount_amount
        vat_amount      = round(after_discount * 0.12, 4) if include_vat else 0.0
        total_amount    = round(after_discount + vat_amount, 2)
        change_amount   = max(0, round(amount_paid - total_amount, 2))

        # Generate unique txn code
        txn_code = generate_txn_code()
        for _ in range(10):
            if not conn.execute("SELECT 1 FROM transactions WHERE transaction_code=?", (txn_code,)).fetchone():
                break
            txn_code = generate_txn_code()

        note_full = notes
        if customer_phone:
            note_full = f"Phone: {customer_phone}" + (f" | {notes}" if notes else "")

        conn.execute("""
            INSERT INTO transactions
              (transaction_code, cashier_id, customer_name, subtotal,
               discount_amount, discount_percent, tax_amount, total_amount,
               amount_paid, change_amount, payment_method, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (txn_code, session['user_id'], customer_name, subtotal,
              discount_amount, discount_pct, vat_amount, total_amount,
              amount_paid, change_amount, payment_method, note_full))
        txn_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Process each item
        for item in items:
            pid = item['product_id']
            qty = item['quantity']
            price = item['price']

            product = conn.execute(
                "SELECT * FROM products WHERE product_id=? AND is_active=1", (pid,)
            ).fetchone()
            if not product:
                conn.rollback()
                return jsonify({'success': False, 'message': f'Product ID {pid} not found'}), 400
            if product['stock'] < qty:
                conn.rollback()
                return jsonify({
                    'success': False,
                    'message': f'Not enough stock for "{product["product_name"]}" '
                               f'(available: {product["stock"]}, requested: {qty})'
                }), 400

            old_stock = product['stock']
            new_stock = old_stock - qty

            # FIFO batch deduction
            remaining = qty
            batch_used = None
            batches = conn.execute("""
                SELECT * FROM product_batches
                WHERE product_id=? AND remaining_quantity>0
                ORDER BY CASE WHEN expiration_date IS NULL THEN 1 ELSE 0 END,
                         expiration_date ASC, batch_id ASC
            """, (pid,)).fetchall()
            for b in batches:
                if remaining <= 0:
                    break
                deduct = min(b['remaining_quantity'], remaining)
                conn.execute(
                    "UPDATE product_batches SET remaining_quantity=remaining_quantity-? WHERE batch_id=?",
                    (deduct, b['batch_id'])
                )
                remaining -= deduct
                batch_used = b['batch_id']

            conn.execute(
                "UPDATE products SET stock=?, updated_at=CURRENT_TIMESTAMP WHERE product_id=?",
                (new_stock, pid)
            )
            conn.execute("""
                INSERT INTO transaction_items
                  (transaction_id, product_id, product_name, quantity, unit_price, discount, total_price, batch_id)
                VALUES (?,?,?,?,?,0,?,?)
            """, (txn_id, pid, product['product_name'], qty, price, price * qty, batch_used))
            conn.execute("""
                INSERT INTO inventory_logs
                  (product_id, user_id, action, quantity_change, quantity_before, quantity_after, reference_id)
                VALUES (?,?,'sale',?,?,?,?)
            """, (pid, session['user_id'], -qty, old_stock, new_stock, txn_code))
            # Product movement record (history)
            conn.execute("""
                INSERT INTO product_movements
                  (product_id, user_id, move_type, quantity, quantity_before, quantity_after,
                   reference_type, reference_id, batch_id, notes)
                VALUES (?,?,'sale',?,?,?,'transaction',?,?,?)
            """, (pid, session['user_id'], -qty, old_stock, new_stock,
                    txn_code, batch_used,
                    f"Sold to {customer_name}"))

        # Audit
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, module, description) VALUES (?,?,?,?)",
            (session['user_id'], 'SALE', 'POS',
             f"Sale {txn_code} — {len(items)} item(s) — ₱{total_amount:.2f} — {payment_method}")
        )
        conn.commit()

        txn   = conn.execute("""
            SELECT t.*, u.full_name as cashier_name
            FROM transactions t JOIN users u ON t.cashier_id=u.user_id
            WHERE t.transaction_id=?
        """, (txn_id,)).fetchone()
        t_items = conn.execute(
            "SELECT * FROM transaction_items WHERE transaction_id=?", (txn_id,)
        ).fetchall()
        conn.close()

        return jsonify({
            'success': True,
            'transaction': dict(txn),
            'items': [dict(i) for i in t_items],
            'vat_amount': vat_amount,
        })
    except Exception as e:
        try: conn.rollback()
        except: pass
        try: conn.close()
        except: pass
        return jsonify({'success': False, 'message': str(e)}), 500

@pos_bp.route('/api/pos/transaction/<int:tid>')
@login_required
def transaction_detail(tid):
    conn = get_db()
    txn   = conn.execute("""
        SELECT t.*, u.full_name as cashier_name
        FROM transactions t JOIN users u ON t.cashier_id=u.user_id
        WHERE t.transaction_id=?
    """, (tid,)).fetchone()
    items = conn.execute(
        "SELECT * FROM transaction_items WHERE transaction_id=?", (tid,)
    ).fetchall()
    conn.close()
    if txn:
        return jsonify({'transaction': dict(txn), 'items': [dict(i) for i in items]})
    return jsonify({'error': 'Not found'}), 404

@pos_bp.route('/api/pos/void/<int:tid>', methods=['POST'])
@login_required
def void_transaction(tid):
    if session.get('role') not in ('admin', 'inventory_manager'):
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    conn = get_db()
    txn = conn.execute("SELECT * FROM transactions WHERE transaction_id=?", (tid,)).fetchone()
    if not txn:
        conn.close()
        return jsonify({'success': False, 'message': 'Transaction not found'}), 404
    if txn['status'] == 'voided':
        conn.close()
        return jsonify({'success': False, 'message': 'Already voided'}), 400
    items = conn.execute(
        "SELECT * FROM transaction_items WHERE transaction_id=?", (tid,)
    ).fetchall()
    try:
        for it in items:
            old = conn.execute(
                "SELECT stock FROM products WHERE product_id=?", (it['product_id'],)
            ).fetchone()
            if old:
                new_s = old['stock'] + it['quantity']
                conn.execute(
                    "UPDATE products SET stock=?, updated_at=CURRENT_TIMESTAMP WHERE product_id=?",
                    (new_s, it['product_id'])
                )
                conn.execute("""
                    INSERT INTO inventory_logs
                      (product_id, user_id, action, quantity_change, quantity_before, quantity_after, reference_id, notes)
                    VALUES (?,?,'return',?,?,?,?,'Voided transaction')
                """, (it['product_id'], session['user_id'], it['quantity'],
                      old['stock'], new_s, txn['transaction_code']))
        conn.execute(
            "UPDATE transactions SET status='voided' WHERE transaction_id=?", (tid,)
        )
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, module, description) VALUES (?,?,?,?)",
            (session['user_id'], 'VOID', 'POS', f"Voided {txn['transaction_code']}")
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback(); conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

@pos_bp.route('/pos/transactions')
@login_required
def transactions():
    conn   = get_db()
    page   = max(1, int(request.args.get('page', 1)))
    per    = 25
    offset = (page - 1) * per
    search    = request.args.get('search', '')
    date_from = request.args.get('date_from', '')
    date_to   = request.args.get('date_to', '')
    status    = request.args.get('status', '')
    payment   = request.args.get('payment', '')

    base  = "FROM transactions t JOIN users u ON t.cashier_id=u.user_id WHERE 1=1"
    params = []
    if search:
        base += " AND (t.transaction_code LIKE ? OR t.customer_name LIKE ?)"
        params += [f'%{search}%', f'%{search}%']
    if date_from:
        base += " AND DATE(t.created_at)>=?"; params.append(date_from)
    if date_to:
        base += " AND DATE(t.created_at)<=?"; params.append(date_to)
    if status:
        base += " AND t.status=?"; params.append(status)
    if payment:
        base += " AND t.payment_method=?"; params.append(payment)

    total   = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
    txns    = conn.execute(
        f"SELECT t.*, u.full_name as cashier_name {base} ORDER BY t.created_at DESC LIMIT {per} OFFSET {offset}",
        params
    ).fetchall()

    # Summary stats for filter range
    stats_row = conn.execute(
        f"SELECT COALESCE(SUM(t.total_amount),0) as rev, COUNT(*) as cnt {base} AND t.status='completed'",
        params
    ).fetchone()

    total_pages = (total + per - 1) // per
    conn.close()
    return render_template('transactions.html',
        txns=txns, page=page, total_pages=total_pages,
        search=search, date_from=date_from, date_to=date_to,
        status=status, payment=payment,
        total=total, stats=dict(stats_row))

@pos_bp.route('/mobile-scan')
@login_required
def mobile_scan():
    return render_template('mobile_scan.html')
