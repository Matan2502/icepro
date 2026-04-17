from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from database import get_connection, init_db
from datetime import datetime, date
import psycopg2.extras
import hashlib
import functools

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'icepro-secret-2026')


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def current_user():
    if 'user_id' not in session:
        return None
    return {
        'id':           session['user_id'],
        'username':     session['username'],
        'display_name': session['display_name'],
        'color':        session['color'],
    }


def rows_to_list(rows):
    result = []
    for row in rows:
        d = {}
        for k, v in dict(row).items():
            if isinstance(v, (datetime, date)):
                d[k] = v.isoformat()
            else:
                d[k] = v
        result.append(d)
    return result


def query(sql, params=(), one=False):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    rows = cur.fetchone() if one else cur.fetchall()
    cur.close(); conn.close()
    return rows


def execute(sql, params=()):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql + " RETURNING id", params)
    last_id = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    return last_id


# ── auth ──────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        pw_hash  = hashlib.sha256(password.encode()).hexdigest()
        user = query("SELECT * FROM users WHERE username=%s AND password_hash=%s",
                     (username, pw_hash), one=True)
        if user:
            session['user_id']      = user['id']
            session['username']     = user['username']
            session['display_name'] = user['display_name']
            session['color']        = user['color']
            return redirect(url_for('dashboard'))
        error = 'שם משתמש או סיסמה שגויים'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── pages ─────────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    me = current_user()
    fridges = query("""
        SELECT f.id, f.name, f.location, f.capacity, COALESCE(i.quantity,0) AS quantity
        FROM fridges f LEFT JOIN inventory i ON i.fridge_id=f.id ORDER BY f.id
    """)
    # כל האירועים — כולם רואים הכל, מסומן מי יצר
    events = query("""
        SELECT e.*, f.name AS fridge_name,
               u.display_name AS creator_name, u.color AS creator_color
        FROM events e
        LEFT JOIN fridges f ON f.id=e.fridge_id
        LEFT JOIN users u ON u.id=e.created_by
        ORDER BY e.event_date LIMIT 8
    """)
    # סיכום אישי
    my_totals = query("""
        SELECT COALESCE(SUM(price),0)::float AS my_revenue,
               COALESCE(SUM(price-quantity*cost_per_unit),0)::float AS my_profit,
               COUNT(*) AS my_events
        FROM events
        WHERE created_by=%s AND to_char(event_date,'YYYY-MM')=to_char(NOW(),'YYYY-MM')
    """, (me['id'],), one=True)
    # סיכום כללי
    totals = query("""
        SELECT COALESCE(SUM(i.quantity),0) AS total_stock,
               (SELECT COUNT(*) FROM events WHERE status!='done') AS active_events,
               (SELECT COALESCE(SUM(price),0)::float FROM events
                WHERE to_char(event_date,'YYYY-MM')=to_char(NOW(),'YYYY-MM')) AS monthly_revenue,
               (SELECT COALESCE(SUM(price-quantity*cost_per_unit),0)::float FROM events
                WHERE to_char(event_date,'YYYY-MM')=to_char(NOW(),'YYYY-MM')) AS monthly_profit
        FROM inventory i
    """, one=True)
    low_fridges = [f for f in fridges if f["quantity"] / f["capacity"] < 0.2]
    users = query("SELECT id, display_name, color FROM users ORDER BY id")
    total_stock_kg = query("""
        SELECT COALESCE(SUM(fs.quantity * bt.weight_kg), 0)::float AS kg
        FROM fridge_stock fs JOIN bag_types bt ON bt.id = fs.bag_type_id
    """, one=True)['kg']
    return render_template("dashboard.html",
                           fridges=fridges, events=events,
                           totals=totals, low_fridges=low_fridges,
                           my_totals=my_totals, me=me, users=users,
                           total_stock_kg=int(total_stock_kg))


@app.route("/inventory")
@login_required
def inventory():
    fridges = query("""
        SELECT f.id, f.name, f.location, f.capacity, COALESCE(i.quantity,0) AS quantity
        FROM fridges f LEFT JOIN inventory i ON i.fridge_id=f.id ORDER BY f.id
    """)
    log = query("""
        SELECT l.*, f.name AS fridge_name, u.display_name AS creator_name, u.color AS creator_color
        FROM inventory_log l
        JOIN fridges f ON f.id=l.fridge_id
        LEFT JOIN users u ON u.id=l.created_by
        ORDER BY l.created_at DESC LIMIT 30
    """)
    # פירוט סוגי שקיות לפי מקרר
    fridge_stock = query("""
        SELECT fs.fridge_id, fs.bag_type_id, fs.quantity,
               bt.name AS bag_name, bt.weight_kg
        FROM fridge_stock fs
        JOIN bag_types bt ON bt.id=fs.bag_type_id
        WHERE fs.quantity > 0
        ORDER BY fs.fridge_id, bt.weight_kg
    """)
    # כל סוגי שקיות קיימים (לבחירה בהוספת מלאי)
    all_bag_types = query("SELECT DISTINCT ON (name, weight_kg) id, name, weight_kg FROM bag_types ORDER BY name, weight_kg")
    # קיבוץ פירוט לפי מקרר
    stock_by_fridge = {}
    for row in fridge_stock:
        fid = row['fridge_id']
        if fid not in stock_by_fridge:
            stock_by_fridge[fid] = []
        stock_by_fridge[fid].append(row)
    return render_template("inventory.html",
                           fridges=fridges, log=log,
                           stock_by_fridge=stock_by_fridge,
                           all_bag_types=rows_to_list(all_bag_types),
                           me=current_user())


@app.route("/events")
@login_required
def events():
    me = current_user()
    status_filter = request.args.get("status", "all")
    user_filter   = request.args.get("user",   "all")
    time_filter   = request.args.get("time",   "all")

    base_q = """
        SELECT e.*, f.name AS fridge_name,
               u.display_name AS creator_name, u.color AS creator_color,
               bt.name AS bag_type_name, bt.weight_kg AS bag_weight_kg
        FROM events e
        LEFT JOIN fridges f ON f.id=e.fridge_id
        LEFT JOIN users u ON u.id=e.created_by
        LEFT JOIN bag_types bt ON bt.id=e.bag_type_id
    """
    conditions, params = [], []

    if status_filter != "all":
        conditions.append("e.status = %s"); params.append(status_filter)
    if user_filter != "all":
        conditions.append("e.created_by = %s"); params.append(int(user_filter))
    if time_filter == "today":
        conditions.append("e.event_date = CURRENT_DATE")
    elif time_filter == "week":
        conditions.append("e.event_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'")
    elif time_filter == "month":
        conditions.append("to_char(e.event_date,'YYYY-MM') = to_char(NOW(),'YYYY-MM')")
    elif time_filter == "future":
        conditions.append("e.event_date >= CURRENT_DATE")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    evts = query(base_q + f" {where} ORDER BY e.event_date DESC", tuple(params))

    fridges   = query("SELECT f.id, f.name, COALESCE(i.quantity,0) AS quantity FROM fridges f LEFT JOIN inventory i ON i.fridge_id=f.id ORDER BY f.name")
    bag_types = query("SELECT * FROM bag_types WHERE user_id=%s ORDER BY weight_kg", (me['id'],))
    all_users = query("SELECT id, display_name, color FROM users ORDER BY id")

    return render_template("events.html",
                           events=evts, fridges=fridges,
                           events_json=rows_to_list(evts),
                           fridges_json=rows_to_list(fridges),
                           bag_types_json=rows_to_list(bag_types),
                           status_filter=status_filter,
                           user_filter=user_filter,
                           time_filter=time_filter,
                           all_users=all_users,
                           me=me)


@app.route("/profit")
@login_required
def profit():
    me          = current_user()
    month       = request.args.get("month", datetime.now().strftime("%Y-%m"))
    user_filter = request.args.get("user", "all")

    uid_clause = "AND created_by=%s" if user_filter != "all" else ""
    uid_param  = (month, int(user_filter)) if user_filter != "all" else (month,)

    row = query(f"""
        SELECT COALESCE(SUM(price),0)::float AS revenue,
               COALESCE(SUM(quantity*cost_per_unit),0)::float AS cost_events
        FROM events WHERE to_char(event_date,'YYYY-MM')=%s AND status='done' {uid_clause}
    """, uid_param, one=True)
    exp_row = query(f"""
        SELECT COALESCE(SUM(amount),0)::float AS total FROM expenses
        WHERE to_char(expense_date,'YYYY-MM')=%s {uid_clause}
    """, uid_param, one=True)

    revenue    = row["revenue"]
    total_cost = row["cost_events"] + exp_row["total"]
    net_profit = revenue - total_cost
    margin     = round((net_profit/revenue*100) if revenue > 0 else 0, 1)

    by_category = query(f"""
        SELECT CASE WHEN name LIKE '%%חתונה%%' THEN 'חתונות'
                    WHEN name LIKE '%%חברה%%' OR name LIKE '%%ארגון%%' THEN 'אירועי חברות'
                    WHEN name LIKE '%%ברביקיו%%' OR name LIKE '%%בריכה%%' THEN 'אירועי פנאי'
                    ELSE 'פרטי / אחר' END AS category,
               SUM(price)::float AS total
        FROM events WHERE to_char(event_date,'YYYY-MM')=%s AND status='done' {uid_clause}
        GROUP BY 1 ORDER BY total DESC
    """, uid_param)

    weekly = query(f"""
        SELECT EXTRACT(WEEK FROM event_date)::int -
               EXTRACT(WEEK FROM date_trunc('month',event_date))::int + 1 AS week_num,
               SUM(price)::float AS total
        FROM events WHERE to_char(event_date,'YYYY-MM')=%s AND status='done' {uid_clause}
        GROUP BY week_num ORDER BY week_num
    """, uid_param)

    expense_list = query(f"""
        SELECT e.*, u.display_name AS creator_name, u.color AS creator_color
        FROM expenses e LEFT JOIN users u ON u.id=e.created_by
        WHERE to_char(expense_date,'YYYY-MM')=%s {uid_clause}
        ORDER BY expense_date DESC
    """, uid_param)

    months = query("SELECT DISTINCT to_char(event_date,'YYYY-MM') AS m FROM events ORDER BY m DESC")
    users  = query("SELECT id, display_name, color FROM users ORDER BY id")
    return render_template("profit.html",
                           revenue=revenue, cost=total_cost,
                           net_profit=net_profit, margin=margin,
                           by_category=by_category, weekly=weekly,
                           expense_list=expense_list, month=month,
                           months=[r["m"] for r in months],
                           users=users, user_filter=user_filter, me=me)


# ── API: stock ────────────────────────────────────────────────────────────────

@app.route("/api/stock/add", methods=["POST"])
@login_required
def api_add_stock():
    data = request.json
    me = current_user()
    fid, qty = int(data["fridge_id"]), int(data["quantity"])
    bag_type_id = data.get("bag_type_id")

    conn = get_connection(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # בדוק קיבולת ומלאי נוכחי
    cur.execute("""
        SELECT f.capacity, COALESCE(i.quantity, 0) AS current_qty
        FROM fridges f LEFT JOIN inventory i ON i.fridge_id = f.id
        WHERE f.id = %s
    """, (fid,))
    fridge = cur.fetchone()
    if not fridge:
        cur.close(); conn.close()
        return jsonify({"ok": False, "error": "מקרר לא נמצא"}), 404

    # חשב תוספת קילוגרם
    if bag_type_id:
        cur.execute("SELECT weight_kg FROM bag_types WHERE id=%s", (int(bag_type_id),))
        bt = cur.fetchone()
        if bt:
            # חשב סה"כ ק"ג נוכחי במקרר
            cur.execute("""
                SELECT COALESCE(SUM(fs.quantity * bt.weight_kg), 0)::float AS current_kg
                FROM fridge_stock fs JOIN bag_types bt ON bt.id = fs.bag_type_id
                WHERE fs.fridge_id = %s
            """, (fid,))
            kg_row = cur.fetchone()
            current_kg = kg_row['current_kg'] if kg_row else 0
            added_kg = qty * float(bt['weight_kg'])
            if current_kg + added_kg > fridge['capacity']:
                cur.close(); conn.close()
                cap = fridge['capacity']
                return jsonify({"ok": False,
                    "error": f"חריגה מהקיבולת! מקרר מכיל כעת {current_kg:.0f} קג, מנסה להוסיף {added_kg:.0f} קג, קיבולת: {cap} קג"}), 400
    else:
        # בלי סוג שקית — בדוק לפי כמות שקיות
        if fridge['current_qty'] + qty > fridge['capacity']:
            cur.close(); conn.close()
            return jsonify({"ok": False,
                "error": f"חריגה מהקיבולת! יש {fridge['current_qty']} שקיות, מנסה להוסיף {qty}, קיבולת: {fridge['capacity']} קג"}), 400

    # עדכן מלאי
    cur2 = conn.cursor()
    cur2.execute("""
        INSERT INTO inventory (fridge_id,quantity) VALUES (%s,%s)
        ON CONFLICT (fridge_id) DO UPDATE SET quantity=inventory.quantity+%s, updated_at=NOW()
    """, (fid, qty, qty))
    cur2.execute("INSERT INTO inventory_log (fridge_id,change,reason,created_by) VALUES (%s,%s,%s,%s)",
                (fid, qty, data.get("reason","קבלת סחורה"), me['id']))
    if bag_type_id:
        cur2.execute("""
            INSERT INTO fridge_stock (fridge_id,bag_type_id,quantity) VALUES (%s,%s,%s)
            ON CONFLICT (fridge_id,bag_type_id) DO UPDATE
            SET quantity=fridge_stock.quantity+%s, updated_at=NOW()
        """, (fid, int(bag_type_id), qty, qty))
    conn.commit(); cur.close(); cur2.close(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/stock/transfer", methods=["POST"])
@login_required
def api_transfer():
    data = request.json
    me = current_user()
    from_id, to_id, qty = int(data["from_fridge"]), int(data["to_fridge"]), int(data["quantity"])
    conn = get_connection(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COALESCE(quantity,0) AS q FROM inventory WHERE fridge_id=%s", (from_id,))
    src = cur.fetchone()
    if not src or src["q"] < qty:
        cur.close(); conn.close()
        return jsonify({"ok": False, "error": "אין מספיק מלאי במקרר המקור"}), 400
    cur.execute("UPDATE inventory SET quantity=quantity-%s, updated_at=NOW() WHERE fridge_id=%s", (qty, from_id))
    cur.execute("""INSERT INTO inventory (fridge_id,quantity) VALUES (%s,%s)
        ON CONFLICT (fridge_id) DO UPDATE SET quantity=inventory.quantity+%s, updated_at=NOW()""", (to_id, qty, qty))
    cur.execute("INSERT INTO inventory_log (fridge_id,change,reason,created_by) VALUES (%s,%s,%s,%s)", (from_id,-qty,f"העברה למקרר {to_id}",me['id']))
    cur.execute("INSERT INTO inventory_log (fridge_id,change,reason,created_by) VALUES (%s,%s,%s,%s)", (to_id,qty,f"קבלה ממקרר {from_id}",me['id']))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


# ── API: events ───────────────────────────────────────────────────────────────

@app.route("/api/events/add", methods=["POST"])
@login_required
def api_add_event():
    d = request.json; me = current_user()
    eid = execute("""
        INSERT INTO events (name,event_date,fridge_id,quantity,price,cost_per_unit,
                            delivery_fee,address,status,notes,created_by,bag_type_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (d["name"], d["event_date"], d.get("fridge_id"),
          int(d["quantity"]), float(d["price"]),
          float(d.get("cost_per_unit",3.5)), float(d.get("delivery_fee",0)),
          d.get("address",""), d.get("status","pending"), d.get("notes",""),
          me['id'], d.get("bag_type_id") or None))
    return jsonify({"ok": True, "id": eid})


@app.route("/api/events/<int:eid>/status", methods=["POST"])
@login_required
def api_event_status(eid):
    new_status = request.json["status"]
    me = current_user()
    conn = get_connection(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM events WHERE id=%s", (eid,))
    evt = cur.fetchone()
    if not evt:
        cur.close(); conn.close()
        return jsonify({"ok": False, "error": "אירוע לא נמצא"}), 404
    if evt["created_by"] and evt["created_by"] != me['id']:
        cur.close(); conn.close()
        return jsonify({"ok": False, "error": "אין הרשאה לשנות אירוע זה"}), 403
    cur.execute("UPDATE events SET status=%s WHERE id=%s", (new_status, eid))
    if new_status == "done":
        cur.execute("SELECT * FROM events WHERE id=%s", (eid,))
        evt = cur.fetchone()
        if evt and evt["fridge_id"]:
            cur.execute("SELECT COALESCE(quantity,0) AS q FROM inventory WHERE fridge_id=%s", (evt["fridge_id"],))
            stock = cur.fetchone()
            available = stock["q"] if stock else 0
            if available < evt["quantity"]:
                conn.rollback(); cur.close(); conn.close()
                return jsonify({"ok": False, "error": f"אין מספיק מלאי. צריך {evt['quantity']}, יש {available}."}), 400
            cur.execute("UPDATE inventory SET quantity=quantity-%s, updated_at=NOW() WHERE fridge_id=%s", (evt["quantity"], evt["fridge_id"]))
            cur.execute("INSERT INTO inventory_log (fridge_id,change,reason,event_id) VALUES (%s,%s,%s,%s)",
                        (evt["fridge_id"], -evt["quantity"], f"אירוע: {evt['name']}", eid))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/events/<int:eid>/edit", methods=["POST"])
@login_required
def api_edit_event(eid):
    d = request.json; me = current_user()
    # וודא שהאירוע שייך למשתמש
    owner = query("SELECT created_by FROM events WHERE id=%s", (eid,), one=True)
    if not owner:
        return jsonify({"ok": False, "error": "אירוע לא נמצא"}), 404
    if owner["created_by"] and owner["created_by"] != me['id']:
        return jsonify({"ok": False, "error": "אין הרשאה לערוך אירוע זה"}), 403
    conn = get_connection(); cur = conn.cursor()
    cur.execute("""UPDATE events SET name=%s,event_date=%s,fridge_id=%s,
               quantity=%s,price=%s,cost_per_unit=%s,delivery_fee=%s,
               address=%s,status=%s,notes=%s,bag_type_id=%s WHERE id=%s""",
               (d["name"], d["event_date"], d.get("fridge_id") or None,
                int(d["quantity"]), float(d["price"]),
                float(d.get("cost_per_unit",3.5)), float(d.get("delivery_fee",0)),
                d.get("address",""), d.get("status","pending"), d.get("notes",""),
                d.get("bag_type_id") or None, eid))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/events/<int:eid>/delete", methods=["POST"])
@login_required
def api_delete_event(eid):
    me = current_user()
    owner = query("SELECT created_by FROM events WHERE id=%s", (eid,), one=True)
    if not owner:
        return jsonify({"ok": False, "error": "אירוע לא נמצא"}), 404
    if owner["created_by"] and owner["created_by"] != me['id']:
        return jsonify({"ok": False, "error": "אין הרשאה למחוק אירוע זה"}), 403
    conn = get_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM inventory_log WHERE event_id=%s", (eid,))
    cur.execute("DELETE FROM events WHERE id=%s", (eid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


# ── API: fridges ──────────────────────────────────────────────────────────────

@app.route("/api/fridges/add", methods=["POST"])
@login_required
def api_add_fridge():
    d = request.json
    fid = execute("INSERT INTO fridges (name,location,capacity) VALUES (%s,%s,%s)",
                  (d["name"], d["location"], int(d.get("capacity",200))))
    execute("INSERT INTO inventory (fridge_id,quantity) VALUES (%s,0)", (fid,))
    return jsonify({"ok": True, "id": fid})


@app.route("/api/fridges/<int:fid>/edit", methods=["POST"])
@login_required
def api_edit_fridge(fid):
    d = request.json
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE fridges SET name=%s,location=%s,capacity=%s WHERE id=%s",
                (d["name"], d["location"], int(d["capacity"]), fid))
    if d.get("quantity") is not None:
        c2 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c2.execute("SELECT COALESCE(quantity,0) AS q FROM inventory WHERE fridge_id=%s", (fid,))
        row = c2.fetchone(); old_qty = row["q"] if row else 0
        new_qty = int(d["quantity"])
        cur.execute("UPDATE inventory SET quantity=%s, updated_at=NOW() WHERE fridge_id=%s", (new_qty, fid))
        cur.execute("INSERT INTO inventory_log (fridge_id,change,reason) VALUES (%s,%s,%s)",
                    (fid, new_qty-old_qty, f"עדכון ידני: {old_qty} ← {new_qty}"))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/fridges/<int:fid>/delete", methods=["POST"])
@login_required
def api_delete_fridge(fid):
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM inventory_log WHERE event_id IN (SELECT id FROM events WHERE fridge_id=%s)", (fid,))
        cur.execute("DELETE FROM events WHERE fridge_id=%s", (fid,))
        cur.execute("DELETE FROM inventory_log WHERE fridge_id=%s", (fid,))
        cur.execute("DELETE FROM inventory WHERE fridge_id=%s", (fid,))
        cur.execute("DELETE FROM fridges WHERE id=%s", (fid,))
        conn.commit()
    except Exception as e:
        conn.rollback(); cur.close(); conn.close()
        return jsonify({"ok": False, "error": str(e)}), 500
    cur.close(); conn.close()
    return jsonify({"ok": True})


# ── API: expenses ─────────────────────────────────────────────────────────────

@app.route("/api/expenses/add", methods=["POST"])
@login_required
def api_add_expense():
    d = request.json; me = current_user()
    eid = execute("INSERT INTO expenses (description,amount,category,expense_date,created_by) VALUES (%s,%s,%s,%s,%s)",
                  (d["description"], float(d["amount"]), d.get("category","general"), d["expense_date"], me['id']))
    return jsonify({"ok": True, "id": eid})


@app.route("/api/expenses/delete/<int:eid>", methods=["POST"])
@login_required
def api_delete_expense(eid):
    conn = get_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE id=%s", (eid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


# ── API: bag_types (מסוננים לפי משתמש) ──────────────────────────────────────

@app.route("/api/bag_types/add", methods=["POST"])
@login_required
def api_add_bag_type():
    d = request.json; me = current_user()
    bid = execute("INSERT INTO bag_types (name,weight_kg,cost_per_kg,price_per_kg,delivery_fee,user_id) VALUES (%s,%s,%s,%s,%s,%s)",
                  (d["name"], float(d["weight_kg"]), float(d["cost_per_kg"]),
                   float(d["price_per_kg"]), float(d["delivery_fee"]), me['id']))
    return jsonify({"ok": True, "id": bid})


@app.route("/api/bag_types/<int:bid>/edit", methods=["POST"])
@login_required
def api_edit_bag_type(bid):
    d = request.json; me = current_user()
    conn = get_connection(); cur = conn.cursor()
    # וודא שהמשתמש עורך רק bag_types שלו
    cur.execute("""UPDATE bag_types SET name=%s,weight_kg=%s,cost_per_kg=%s,
                   price_per_kg=%s,delivery_fee=%s,updated_at=NOW()
                   WHERE id=%s AND user_id=%s""",
                (d["name"], float(d["weight_kg"]), float(d["cost_per_kg"]),
                 float(d["price_per_kg"]), float(d["delivery_fee"]), bid, me['id']))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/bag_types/<int:bid>/delete", methods=["POST"])
@login_required
def api_delete_bag_type(bid):
    me = current_user()
    conn = get_connection(); cur = conn.cursor()
    # מחק רק bag_types של המשתמש
    cur.execute("DELETE FROM bag_types WHERE id=%s AND user_id=%s", (bid, me['id']))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/costs/calc", methods=["POST"])
@login_required
def api_calc_cost():
    d = request.json
    bag = query("SELECT * FROM bag_types WHERE id=%s", (int(d["bag_type_id"]),), one=True)
    if not bag:
        return jsonify({"ok": False, "error": "סוג שקית לא נמצא"}), 404
    qty = int(d["quantity"]); w = float(bag["weight_kg"])
    tc = qty * w * float(bag["cost_per_kg"])
    dv = float(bag["delivery_fee"]) if d.get("with_delivery") else 0
    tp = qty * w * float(bag["price_per_kg"]) + dv
    profit = tp - tc
    return jsonify({"ok": True,
                    "cost_per_unit":  round(w*float(bag["cost_per_kg"]),2),
                    "price_per_unit": round(w*float(bag["price_per_kg"]),2),
                    "total_cost": round(tc,2), "total_price": round(tp,2),
                    "delivery_fee": round(dv,2), "profit": round(profit,2),
                    "margin": round(profit/tp*100,1) if tp>0 else 0})


# ── calendar ──────────────────────────────────────────────────────────────────

@app.route("/calendar")
@login_required
def calendar_view():
    me    = current_user()
    year  = request.args.get("year",  datetime.now().year,  type=int)
    month = request.args.get("month", datetime.now().month, type=int)
    if month == 1:  prev_year, prev_month = year-1, 12
    else:           prev_year, prev_month = year, month-1
    if month == 12: next_year, next_month = year+1, 1
    else:           next_year, next_month = year, month+1
    evts = query("""
        SELECT e.*, f.name AS fridge_name,
               u.display_name AS creator_name, u.color AS creator_color,
               bt.name AS bag_type_name, bt.weight_kg AS bag_weight_kg
        FROM events e LEFT JOIN fridges f ON f.id=e.fridge_id
        LEFT JOIN users u ON u.id=e.created_by
        LEFT JOIN bag_types bt ON bt.id=e.bag_type_id
        WHERE EXTRACT(YEAR FROM event_date)=%s AND EXTRACT(MONTH FROM event_date)=%s
        ORDER BY event_date, e.id
    """, (year, month))
    fridges   = query("SELECT f.id, f.name, COALESCE(i.quantity,0) AS quantity FROM fridges f LEFT JOIN inventory i ON i.fridge_id=f.id ORDER BY f.name")
    bag_types = query("SELECT * FROM bag_types WHERE user_id=%s ORDER BY weight_kg", (me['id'],))
    total_stock = query("SELECT COALESCE(SUM(quantity),0)::int AS total FROM inventory", one=True)['total']
    total_stock_kg = query("""
        SELECT COALESCE(SUM(fs.quantity * bt.weight_kg), 0)::float AS kg
        FROM fridge_stock fs JOIN bag_types bt ON bt.id = fs.bag_type_id
    """, one=True)['kg']
    return render_template("calendar.html",
                           year=year, month=month,
                           prev_year=prev_year, prev_month=prev_month,
                           next_year=next_year, next_month=next_month,
                           events_json=rows_to_list(evts),
                           fridges_json=rows_to_list(fridges),
                           bag_types_json=rows_to_list(bag_types),
                           total_stock=total_stock,
                           total_stock_kg=total_stock_kg,
                           me=me)


# ── costs ─────────────────────────────────────────────────────────────────────

@app.route("/costs")
@login_required
def costs():
    me = current_user()
    # bag_types — רק של המשתמש הנוכחי
    bag_types = query("SELECT * FROM bag_types WHERE user_id=%s ORDER BY weight_kg", (me['id'],))
    # הוצאות — רק של המשתמש הנוכחי
    expense_list = query("""
        SELECT e.*, u.display_name AS creator_name, u.color AS creator_color
        FROM expenses e LEFT JOIN users u ON u.id=e.created_by
        WHERE e.created_by=%s ORDER BY expense_date DESC LIMIT 50
    """, (me['id'],))
    totals = query("""
        SELECT category, SUM(amount)::float AS total FROM expenses
        WHERE to_char(expense_date,'YYYY-MM')=to_char(NOW(),'YYYY-MM') AND created_by=%s
        GROUP BY category ORDER BY total DESC
    """, (me['id'],))
    monthly = query("""
        SELECT to_char(expense_date,'YYYY-MM') AS month, SUM(amount)::float AS total
        FROM expenses WHERE created_by=%s GROUP BY 1 ORDER BY 1 DESC LIMIT 6
    """, (me['id'],))
    return render_template("costs.html",
                           bag_types=bag_types,
                           bag_types_json=rows_to_list(bag_types),
                           expense_list=expense_list,
                           totals=totals, monthly=monthly, me=me)


# ── run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("IcePro מופעל על http://127.0.0.1:5000")
    app.run(debug=True)
