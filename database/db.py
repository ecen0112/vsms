import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'vsms.db')

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','inventory_manager','cashier')),
            email TEXT,
            phone TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_person TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            barcode TEXT UNIQUE,
            category TEXT NOT NULL,
            brand TEXT,
            description TEXT,
            price REAL NOT NULL DEFAULT 0,
            cost_price REAL NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0,
            unit TEXT DEFAULT 'pcs',
            low_stock_threshold INTEGER DEFAULT 10,
            image TEXT,
            supplier_id INTEGER,
            requires_prescription INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
        );

        CREATE TABLE IF NOT EXISTS product_batches (
            batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            batch_number TEXT NOT NULL,
            expiration_date DATE,
            quantity INTEGER NOT NULL DEFAULT 0,
            remaining_quantity INTEGER NOT NULL DEFAULT 0,
            supplier_id INTEGER,
            purchase_price REAL,
            date_received DATE DEFAULT CURRENT_DATE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(product_id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_code TEXT UNIQUE NOT NULL,
            cashier_id INTEGER NOT NULL,
            customer_name TEXT DEFAULT 'Walk-in Customer',
            subtotal REAL NOT NULL DEFAULT 0,
            discount_amount REAL DEFAULT 0,
            discount_percent REAL DEFAULT 0,
            tax_amount REAL DEFAULT 0,
            total_amount REAL NOT NULL DEFAULT 0,
            amount_paid REAL DEFAULT 0,
            change_amount REAL DEFAULT 0,
            payment_method TEXT DEFAULT 'cash',
            status TEXT DEFAULT 'completed',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cashier_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS transaction_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            discount REAL DEFAULT 0,
            total_price REAL NOT NULL,
            batch_id INTEGER,
            FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE IF NOT EXISTS inventory_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('stock_in','stock_out','adjustment','sale','return')),
            quantity_change INTEGER NOT NULL,
            quantity_before INTEGER NOT NULL,
            quantity_after INTEGER NOT NULL,
            reference_id TEXT,
            batch_id INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(product_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            module TEXT NOT NULL,
            description TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );


        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT UNIQUE NOT NULL,
            supplier_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            approved_by INTEGER,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','partial','arrived','approved','cancelled')),
            expected_date DATE,
            arrived_date DATE,
            notes TEXT,
            total_amount REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
            FOREIGN KEY (created_by) REFERENCES users(user_id),
            FOREIGN KEY (approved_by) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS purchase_order_items (
            poi_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity_ordered INTEGER NOT NULL DEFAULT 0,
            quantity_received INTEGER NOT NULL DEFAULT 0,
            unit_cost REAL NOT NULL DEFAULT 0,
            expiration_date DATE,
            batch_number TEXT,
            notes TEXT,
            FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE IF NOT EXISTS product_movements (
            move_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            move_type TEXT NOT NULL
                CHECK(move_type IN ('sale','stock_in','adjustment','damaged','returned','expired_removal','transfer','initial')),
            quantity INTEGER NOT NULL,
            quantity_before INTEGER NOT NULL,
            quantity_after INTEGER NOT NULL,
            unit_cost REAL DEFAULT 0,
            reference_type TEXT,
            reference_id TEXT,
            batch_id INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(product_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL CHECK(alert_type IN ('low_stock','expiring','expired','reorder')),
            product_id INTEGER,
            batch_id INTEGER,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
    ''')

    # Seed default admin user
    existing = c.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    if not existing:
        c.execute("""
            INSERT INTO users (username, password, full_name, role, email)
            VALUES (?, ?, ?, ?, ?)
        """, ('admin', generate_password_hash('admin123'), 'System Administrator', 'admin', 'admin@vsms.com'))

        c.execute("""
            INSERT INTO users (username, password, full_name, role, email)
            VALUES (?, ?, ?, ?, ?)
        """, ('manager', generate_password_hash('manager123'), 'Inventory Manager', 'inventory_manager', 'manager@vsms.com'))

        c.execute("""
            INSERT INTO users (username, password, full_name, role, email)
            VALUES (?, ?, ?, ?, ?)
        """, ('cashier', generate_password_hash('cashier123'), 'Cashier Staff', 'cashier', 'cashier@vsms.com'))

    # Seed sample suppliers
    supplier_count = c.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
    if supplier_count == 0:
        suppliers = [
            ('VetPharma Inc.', 'John Dela Cruz', '09171234567', 'sales@vetpharma.com', 'Manila, Philippines', 'Main pharmaceutical supplier'),
            ('PetNutrition Corp.', 'Maria Santos', '09281234567', 'orders@petnutrition.com', 'Quezon City, Philippines', 'Pet food and supplements'),
            ('MedVet Supplies', 'Carlos Reyes', '09351234567', 'supply@medvet.com', 'Makati, Philippines', 'Medical equipment'),
        ]
        for s in suppliers:
            c.execute("INSERT INTO suppliers (name, contact_person, phone, email, address, notes) VALUES (?,?,?,?,?,?)", s)

    # Seed sample products
    product_count = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if product_count == 0:
        products = [
            ('Amoxicillin 500mg', '8901234560001', 'Veterinary Medicines', 'VetPharma', 'Broad-spectrum antibiotic', 45.00, 28.00, 150, 'tablet', 20, None, 1, 1),
            ('Ivermectin 1%', '8901234560002', 'Veterinary Medicines', 'MedVet', 'Anti-parasitic solution', 220.00, 140.00, 80, 'bottle', 15, None, 3, 1),
            ('Rabies Vaccine', '8901234560003', 'Vaccines', 'VetPharma', 'Annual rabies prevention vaccine', 350.00, 210.00, 45, 'vial', 10, None, 1, 1),
            ('5-in-1 Dog Vaccine', '8901234560004', 'Vaccines', 'VetPharma', 'DHPP combination vaccine', 480.00, 290.00, 30, 'vial', 10, None, 1, 1),
            ('Omega-3 Fish Oil', '8901234560005', 'Pet Supplements', 'PetNutrition', 'Coat and skin health supplement', 180.00, 95.00, 120, 'bottle', 25, None, 2, 0),
            ('Vitamin B Complex', '8901234560006', 'Pet Supplements', 'VetPharma', 'Energy and immune support', 95.00, 55.00, 200, 'tablet', 30, None, 1, 0),
            ('Royal Canin Medium Adult', '8901234560007', 'Pet Food', 'Royal Canin', 'Complete dry food for medium dogs', 1250.00, 880.00, 60, 'bag', 15, None, 2, 0),
            ('Whiskas Tuna 85g', '8901234560008', 'Pet Food', 'Whiskas', 'Wet cat food in tuna flavor', 35.00, 22.00, 180, 'pouch', 40, None, 2, 0),
            ('Digital Thermometer', '8901234560009', 'Veterinary Equipment', 'MedVet', 'Veterinary rectal thermometer', 380.00, 200.00, 25, 'piece', 5, None, 3, 0),
            ('Stethoscope Pro', '8901234560010', 'Veterinary Equipment', 'MedVet', 'Professional veterinary stethoscope', 1800.00, 1100.00, 10, 'piece', 3, None, 3, 0),
        ]
        for p in products:
            c.execute("""INSERT INTO products 
                (product_name, barcode, category, brand, description, price, cost_price, 
                 stock, unit, low_stock_threshold, image, supplier_id, requires_prescription)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", p)

        # Seed batches for products
        from datetime import date, timedelta
        today = date.today()
        batches = [
            (1, 'BATCH-AMX-001', (today + timedelta(days=365)).isoformat(), 150, 150, 1),
            (2, 'BATCH-IVR-001', (today + timedelta(days=180)).isoformat(), 80, 80, 3),
            (3, 'BATCH-RAB-001', (today + timedelta(days=90)).isoformat(), 45, 45, 1),
            (4, 'BATCH-5IN1-001', (today + timedelta(days=120)).isoformat(), 30, 30, 1),
            (5, 'BATCH-OMG-001', (today + timedelta(days=300)).isoformat(), 120, 120, 2),
            (6, 'BATCH-VTB-001', (today + timedelta(days=400)).isoformat(), 200, 200, 1),
            (7, 'BATCH-RC-001', (today + timedelta(days=240)).isoformat(), 60, 60, 2),
            (8, 'BATCH-WSK-001', (today + timedelta(days=180)).isoformat(), 180, 180, 2),
            (9, 'BATCH-THERM-001', None, 25, 25, 3),
            (10, 'BATCH-STETH-001', None, 10, 10, 3),
        ]
        for b in batches:
            c.execute("""INSERT INTO product_batches 
                (product_id, batch_number, expiration_date, quantity, remaining_quantity, supplier_id)
                VALUES (?,?,?,?,?,?)""", b)

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")
