import psycopg2
import psycopg2.extras
import hashlib
import os


def get_connection():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        return psycopg2.connect(db_url)
    return psycopg2.connect(
        host='localhost', port='5432',
        dbname='icepro', user='postgres', password='12345678'
    )


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          SERIAL PRIMARY KEY,
            username    TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            color       TEXT NOT NULL DEFAULT '#1D9E75',
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        import hashlib
        users = [
            ('matan',  'מתן',  hashlib.sha256('matan123'.encode()).hexdigest(),  '#1D9E75'),
            ('lior',   'ליאור', hashlib.sha256('lior123'.encode()).hexdigest(),   '#7F77DD'),
        ]
        for u in users:
            c.execute("""
                INSERT INTO users (username, display_name, password_hash, color)
                VALUES (%s,%s,%s,%s)
            """, u)

    c.execute("""
        CREATE TABLE IF NOT EXISTS fridges (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            location    TEXT NOT NULL,
            capacity    INTEGER NOT NULL DEFAULT 200,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id          SERIAL PRIMARY KEY,
            fridge_id   INTEGER NOT NULL REFERENCES fridges(id),
            quantity    INTEGER NOT NULL DEFAULT 0,
            updated_at  TIMESTAMP DEFAULT NOW(),
            UNIQUE (fridge_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id              SERIAL PRIMARY KEY,
            name            TEXT NOT NULL,
            event_date      DATE NOT NULL,
            fridge_id       INTEGER REFERENCES fridges(id),
            quantity        INTEGER NOT NULL,
            price           NUMERIC(10,2) NOT NULL,
            cost_per_unit   NUMERIC(10,2) NOT NULL DEFAULT 3.5,
            delivery_fee    NUMERIC(10,2) NOT NULL DEFAULT 0,
            address         TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            notes           TEXT,
            created_by      INTEGER REFERENCES users(id),
            created_at      TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS delivery_fee NUMERIC(10,2) NOT NULL DEFAULT 0")
    c.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS address TEXT")
    c.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id)")
    c.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS bag_type_id INTEGER REFERENCES bag_types(id)")

    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory_log (
            id          SERIAL PRIMARY KEY,
            fridge_id   INTEGER NOT NULL REFERENCES fridges(id),
            change      INTEGER NOT NULL,
            reason      TEXT,
            event_id    INTEGER REFERENCES events(id),
            created_by  INTEGER REFERENCES users(id),
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("ALTER TABLE inventory_log ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id)")

    c.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id           SERIAL PRIMARY KEY,
            description  TEXT NOT NULL,
            amount       NUMERIC(10,2) NOT NULL,
            category     TEXT NOT NULL DEFAULT 'general',
            expense_date DATE NOT NULL,
            created_by   INTEGER REFERENCES users(id),
            created_at   TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id)")

    c.execute("""
        CREATE TABLE IF NOT EXISTS bag_types (
            id              SERIAL PRIMARY KEY,
            name            TEXT NOT NULL,
            weight_kg       NUMERIC(5,2) NOT NULL,
            cost_per_kg     NUMERIC(10,2) NOT NULL DEFAULT 0,
            price_per_kg    NUMERIC(10,2) NOT NULL DEFAULT 0,
            delivery_fee    NUMERIC(10,2) NOT NULL DEFAULT 0,
            user_id         INTEGER REFERENCES users(id),
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("ALTER TABLE bag_types ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)")

    c.execute("""
        CREATE TABLE IF NOT EXISTS fridge_stock (
            id          SERIAL PRIMARY KEY,
            fridge_id   INTEGER NOT NULL REFERENCES fridges(id),
            bag_type_id INTEGER NOT NULL REFERENCES bag_types(id),
            quantity    INTEGER NOT NULL DEFAULT 0,
            updated_at  TIMESTAMP DEFAULT NOW(),
            UNIQUE (fridge_id, bag_type_id)
        )
    """)

    c.execute("SELECT COUNT(*) FROM bag_types")
    if c.fetchone()[0] == 0:
        c.execute("SELECT id FROM users ORDER BY id")
        user_ids = [r[0] for r in c.fetchall()]
        for uid in user_ids:
            c.execute("""
                INSERT INTO bag_types (name, weight_kg, cost_per_kg, price_per_kg, delivery_fee, user_id)
                VALUES
                    ('שקית 2 קילו', 2, 4.0, 8.0, 0, %s),
                    ('שקית 8 קילו', 8, 3.5, 7.0, 0, %s)
            """, (uid, uid))

    conn.commit()
    c.close()
    conn.close()
