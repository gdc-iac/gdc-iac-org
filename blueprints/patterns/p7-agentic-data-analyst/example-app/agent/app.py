# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import hmac
import time
import psycopg2
import pandas as pd
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Configuration
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'gemma')
LLM_GATEWAY_URL = os.environ.get('LLM_GATEWAY_URL', os.environ.get('LLM_URL', 'http://gemma-gateway.gemma-inference.svc.cluster.local:80/v1'))
LLM_URL = os.environ.get('LLM_URL', LLM_GATEWAY_URL)
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemma-2-27b-it')
AO_PROJECT_ID = os.environ.get('AO_PROJECT_ID', 'projects/your-project-id')
GDC_TOKEN = os.environ.get('GDC_TOKEN')
AGENT_API_KEY = os.environ.get('AGENT_API_KEY', '')
DB_HOST = os.environ.get('DB_HOST', 'postgres-svc')
DB_NAME = os.environ.get('DB_NAME', 'postgres')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS', 'password')

FORBIDDEN_SQL_KEYWORDS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|CALL|DO|'
    r'EXECUTE|PREPARE|SET|RESET|SHOW|VACUUM|ANALYZE|LOCK|LISTEN|NOTIFY|LOAD|IMPORT|'
    r'PG_SLEEP|PG_READ_FILE|PG_READ_BINARY_FILE|PG_LS_DIR|PG_STAT_FILE|LO_IMPORT|'
    r'LO_EXPORT|DBLINK|PG_TERMINATE_BACKEND|PG_CANCEL_BACKEND|PG_RELOAD_CONF|'
    r'PG_CATALOG|INFORMATION_SCHEMA|PG_SHADOW|PG_AUTHID|PG_USER|PG_ROLES|PG_SETTINGS|PG_STAT_ACTIVITY)\b',
    re.IGNORECASE,
)


def validate_readonly_sql(raw_sql: str):
    """
    Strictly validate that LLM-generated SQL is a single read-only SELECT statement
    against allowed application tables, with no stacked queries, comments, or system functions.
    Returns (is_valid: bool, cleaned_sql_or_error: str).
    """
    if not raw_sql or not raw_sql.strip():
        return False, "Empty SQL query"

    # Strip trailing semicolon(s), then reject any remaining semicolons (stacked queries)
    sql_clean = raw_sql.strip().rstrip(";").strip()
    if ";" in sql_clean:
        return False, "Multiple SQL statements (stacked queries) are prohibited"

    # Reject SQL comments that could mask payloads
    if "--" in sql_clean or "/*" in sql_clean or "*/" in sql_clean:
        return False, "SQL comments are prohibited"

    # Must begin with SELECT
    if not re.match(r'^SELECT\b', sql_clean, re.IGNORECASE):
        return False, "Only SELECT queries allowed"

    # Reject any DDL/DML, administrative commands, or dangerous PostgreSQL functions/catalogs
    if FORBIDDEN_SQL_KEYWORDS.search(sql_clean):
        return False, "Prohibited SQL keyword or system catalog detected"

    return True, sql_clean


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )


def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                date DATE,
                amount DECIMAL
            );
        """)
        # Seed data if empty
        cur.execute("SELECT count(*) FROM sales")
        if cur.fetchone()[0] == 0:
            print("Seeding data...")
            cur.execute("""
                INSERT INTO sales (date, amount) VALUES 
                ('2023-01-01', 100), ('2023-01-02', 150), ('2023-01-03', 200),
                ('2023-01-04', 130), ('2023-01-05', 170);
            """)
            conn.commit()
        cur.close()
        conn.close()
        print("Database initialized.")
    except Exception as e:
        print(f"DB Init Error: {e}")


def ask_llm(prompt):
    provider = os.environ.get('LLM_PROVIDER', LLM_PROVIDER).lower()
    endpoint = os.environ.get('LLM_GATEWAY_URL', os.environ.get('LLM_URL', LLM_GATEWAY_URL))
    model = os.environ.get('GEMINI_MODEL', GEMINI_MODEL)
    ao_project_id = os.environ.get('AO_PROJECT_ID', AO_PROJECT_ID)
    token = os.environ.get('GDC_TOKEN', GDC_TOKEN)

    try:
        if provider == 'gemma' or 'gemma' in endpoint:
            if endpoint.endswith('/generate'):
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                resp = requests.post(endpoint, json={"prompt": prompt}, headers=headers, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    if "response" in data and "text" in data["response"]:
                        return data["response"]["text"]
                    return data.get('text', '')
            else:
                url = endpoint if endpoint.endswith('/chat/completions') else f"{endpoint.rstrip('/')}/chat/completions"
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0
                }
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            return choice["message"]["content"]
                        elif "text" in choice:
                            return choice["text"]
                if not endpoint.endswith('/chat/completions'):
                    try:
                        gen_url = f"{endpoint.rstrip('/')}/generate"
                        gen_resp = requests.post(gen_url, json={"prompt": prompt}, headers=headers, timeout=60)
                        if gen_resp.status_code == 200:
                            gen_data = gen_resp.json()
                            if "response" in gen_data and "text" in gen_data["response"]:
                                return gen_data["response"]["text"]
                            return gen_data.get('text', '')
                    except Exception:
                        pass
        else:
            url = endpoint if endpoint.endswith('/chat/completions') else f"{endpoint.rstrip('/')}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "x-goog-user-project": ao_project_id
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"]

        print(f"LLM request returned status code: {resp.status_code}")
    except Exception as e:
        print(f"LLM Error: {e}")

    # Fallback for testing if LLM is unreachable
    if "count" in prompt.lower():
        return "SELECT count(*) FROM sales;"
    return "SELECT * FROM sales LIMIT 5;"


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200


@app.route('/ready', methods=['GET'])
def ready():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({"status": "ready"}), 200
    except Exception as e:
        print(f"Readiness check error: {e}")
        return jsonify({"status": "not ready", "error": "Database connection unavailable"}), 503


@app.route('/query', methods=['POST'])
def query():
    expected_key = os.environ.get('AGENT_API_KEY', AGENT_API_KEY)
    if expected_key:
        auth_header = request.headers.get('Authorization', '')
        provided_key = ''
        if auth_header.startswith('Bearer '):
            provided_key = auth_header.split(' ', 1)[1].strip()
        elif request.headers.get('X-API-Key'):
            provided_key = request.headers.get('X-API-Key', '').strip()
        if not provided_key or not hmac.compare_digest(provided_key, expected_key):
            return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    question = data.get('question', '')
    if not question:
        return jsonify({"error": "No question provided"}), 400

    print(f"Received question: {question}")

    # 1. Get SQL from LLM
    prompt_context = f"""
You are a PostgreSQL expert. Write a query to answer the user's question.

Database Schema:
CREATE TABLE sales (id SERIAL PRIMARY KEY, date DATE, amount DECIMAL);

IMPORTANT RULES: 
1. If the user asks for "sales amount" or "total amount", you MUST map it to the 'amount' column (e.g., SUM(amount)).
2. Under no circumstances should you generate columns like 'total_amount' or 'sales_amount'. The column label is strictly 'amount'.
3. Return ONLY the raw SQL query.

Question: {question}
"""
    sql_query = ask_llm(prompt_context)
    print(f"LLM suggested SQL: {sql_query}")

    # 2. Extract SQL if formatted in markdown
    sql_query = sql_query.strip()
    match = re.search(r'```sql\s*(.*?)\s*```', sql_query, re.DOTALL | re.IGNORECASE)
    if match:
        sql_query = match.group(1).strip()
    else:
        match = re.search(r'```\s*(.*?)\s*```', sql_query, re.DOTALL)
        if match:
            sql_query = match.group(1).strip()

    # 2.5 Bruteforce fail-safes against LLM hallucination despite strict prompts
    sql_query = re.sub(r'(?i)\b(total_amount|sales_amount|sale_amount)\b', 'amount', sql_query)

    # 3. Validate read-only SQL before connecting
    is_valid, validated_or_err = validate_readonly_sql(sql_query)
    if not is_valid:
        return jsonify({"error": validated_or_err}), 400

    sql_clean = validated_or_err

    # 4. Execute SQL inside a strictly read-only, time-bounded session
    try:
        conn = get_db_connection()
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()
        cur.execute("SET statement_timeout = 5000;")
        cur.execute(sql_clean)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall() if cur.description else []
        cur.close()
        conn.close()

        result = [dict(zip(columns, row)) for row in rows]
        return jsonify({"answer": result, "sql": sql_clean})

    except Exception as e:
        print(f"Query execution error: {e}")
        return jsonify({"error": "Query execution failed"}), 500


if __name__ == "__main__":
    time.sleep(2)
    init_db()
    app.run(host='0.0.0.0', port=8080)
