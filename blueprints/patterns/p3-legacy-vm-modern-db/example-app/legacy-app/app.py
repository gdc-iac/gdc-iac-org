import psycopg2
import time
import os
import random
from datetime import datetime

# Simulating a legacy monolithic application that processes "orders"
# It runs a continuous loop, connecting to the "Modern DB" (PostgreSQL)

from psycopg2 import pool

# Database connection pool
db_pool = None

def get_db_connection():
    global db_pool
    if db_pool is None:
        try:
            db_pool = pool.SimpleConnectionPool(
                1, 10,
                host=os.environ.get('DB_HOST', 'localhost'),
                database=os.environ.get('DB_NAME', 'legacy_db'),
                user=os.environ.get('DB_USER', 'postgres'),
                password=os.environ.get('DB_PASS', 'password')
            )
        except Exception as e:
            print(f"Error creating connection pool: {e}")
            raise e
    return db_pool.getconn()

def return_db_connection(conn):
    if db_pool:
        db_pool.putconn(conn)

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                product_id INT NOT NULL,
                quantity INT NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        return_db_connection(conn)
        print("Database initialized.")
    except Exception as e:
        print(f"Database initialization warning (ignoring): {e}")

def process_orders():
    while True:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Simulate processing an order
            product_id = random.randint(100, 999)
            quantity = random.randint(1, 10)
            
            cur.execute(
                "INSERT INTO orders (product_id, quantity) VALUES (%s, %s) RETURNING id;",
                (product_id, quantity)
            )
            order_id = cur.fetchone()[0]
            conn.commit()
            
            print(f"[{datetime.now()}] Processed order #{order_id} for product {product_id} (Qty: {quantity})")
            
            cur.close()
            
        except Exception as e:
            print(f"Error processing order: {e}")
        finally:
            if 'conn' in locals():
                return_db_connection(conn)
        
        # Simulate some processing time
        time.sleep(5)

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    print("Starting Legacy Order Processor...")
    # Wait for DB
    time.sleep(5)
    try:
        init_db()
        process_orders()
    except Exception as e:
        print(f"Fatal error: {e}")
