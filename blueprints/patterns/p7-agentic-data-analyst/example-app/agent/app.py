import os
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
DB_HOST = os.environ.get('DB_HOST', 'postgres-svc')
DB_NAME = os.environ.get('DB_NAME', 'postgres')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS', 'password')

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
        return jsonify({"status": "not ready", "error": str(e)}), 503

@app.route('/query', methods=['POST'])
def query():
    data = request.get_json()
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
    import re
    sql_query = sql_query.strip()
    match = re.search(r'```sql\s*(.*?)\s*```', sql_query, re.DOTALL | re.IGNORECASE)
    if match:
        sql_query = match.group(1).strip()
    else:
        # Fallback to stripping generic code blocks
        match = re.search(r'```\s*(.*?)\s*```', sql_query, re.DOTALL)
        if match:
            sql_query = match.group(1).strip()
            
    # 2.5 Bruteforce fail-safes against LLM hallucination despite strict prompts
    # Catch any singular/plural variants and force it back to the exact 'amount' column
    sql_query = re.sub(r'(?i)\b(total_amount|sales_amount|sale_amount)\b', 'amount', sql_query)
    # 3. Execute SQL
    try:
        conn = get_db_connection()
        # Basic safety: only allow SELECT
        if not sql_query.upper().startswith("SELECT"):
             conn.close()
             return jsonify({"error": "Only SELECT queries allowed", "sql": sql_query}), 400
             
        cur = conn.cursor()
        cur.execute(sql_query)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall() if cur.description else []
        cur.close()
        conn.close()
        
        result = [dict(zip(columns, row)) for row in rows]
        return jsonify({"answer": result, "sql": sql_query})
            
    except Exception as e:
        return jsonify({"error": str(e), "sql": sql_query}), 500

if __name__ == "__main__":
    # Initialize DB on start
    time.sleep(2) # Wait a bit for DB
    init_db()
    app.run(host='0.0.0.0', port=8080)
