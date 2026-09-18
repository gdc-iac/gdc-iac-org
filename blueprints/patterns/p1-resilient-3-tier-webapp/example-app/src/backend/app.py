import os
import time
import psycopg2
from psycopg2 import pool
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)

# Restrict CORS
allowed_origins = os.environ.get('ALLOWED_ORIGINS', '*').split(',')
CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

# Database connection pool
db_pool = None

def get_db_connection():
    global db_pool
    if db_pool is None:
        try:
            db_pool = psycopg2.pool.SimpleConnectionPool(
                1, 20,
                host=os.environ.get('DB_HOST', 'localhost'),
                database=os.environ.get('DB_NAME', 'todos'),
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

@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/api/todos', methods=['GET'])
def get_todos():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('SELECT id, title, completed FROM todos;')
        todos = cur.fetchall()
        cur.close()
        return jsonify([{'id': t[0], 'title': t[1], 'completed': t[2]} for t in todos])
    finally:
        return_db_connection(conn)

@app.route('/api/todos', methods=['POST'])
def add_todo():
    data = request.json
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('INSERT INTO todos (title, completed) VALUES (%s, %s) RETURNING id;',
                    (data['title'], False))
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        return jsonify({'id': new_id, 'title': data['title'], 'completed': False}), 201
    finally:
        return_db_connection(conn)

def init_db():
    retries = 5
    while retries > 0:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('CREATE TABLE IF NOT EXISTS todos (id SERIAL PRIMARY KEY, title TEXT NOT NULL, completed BOOLEAN NOT NULL);')
            conn.commit()
            cur.close()
            return_db_connection(conn)
            print("Database initialized successfully.")
            return
        except Exception as e:
            print(f"Database not ready, retrying... ({retries} left) Error: {e}")
            retries -= 1
            time.sleep(5)
    print("Failed to initialize database after retries.")

if __name__ == '__main__':
    # In production (gunicorn), this block is not executed.
    # Initialization should ideally happen in a separate migration job, 
    # but for this simple app we'll keep it here or rely on the first request/external init.
    # However, gunicorn loads the app object, so we can run init_db() on module load if we want,
    # but that might be risky with multiple workers. 
    # For this pattern, we'll call init_db() if run directly.
    init_db()
    app.run(host='0.0.0.0', port=8080)
else:
    # When running with gunicorn, try to init db once on startup of the worker
    # Note: In a real production app, use a migration tool (Flyway, Liquibase, Alembic)
    # running as a Kubernetes Job.
    try:
        init_db()
    except Exception as e:
        print(f"Warning: DB init failed during startup: {e}")
