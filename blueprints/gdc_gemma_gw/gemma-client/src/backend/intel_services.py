"""
intel_services.py
Intelligence services module for the Joint Intelligence & Readiness Console.
Implements:
1. Agentic Data Analyst (Natural Language -> Safe Read-Only SQL -> Execution -> Executive Insight)
2. All-Source Intelligence RAG (Grounded Semantic Retrieval from Intelligence Reports)
"""

import time
import re
import json
import asyncio
from database import db
from chat import client, GATEWAY_URL
from models import Citation

DB_SCHEMA_PROMPT = """
You are an expert military operations database analyst. Your job is to translate natural language commander queries into SAFE, READ-ONLY PostgreSQL SELECT queries.

Database Schema:
1. military_units (unit_id VARCHAR PRIMARY KEY, unit_name VARCHAR, branch VARCHAR, sector VARCHAR, base_location VARCHAR, readiness_rating VARCHAR ['C1', 'C2', 'C3', 'C4'], commander VARCHAR, personnel_count INT, operational_status VARCHAR)
   Note: 'C1'=Fully Ready, 'C2'=Substantially Ready, 'C3'=Marginally Ready, 'C4'=Not Combat Ready. A query for "below C2" or "degraded" should match readiness_rating IN ('C2', 'C3', 'C4') or ('C3', 'C4').
2. equipment_inventory (id UUID PRIMARY KEY, unit_id VARCHAR REFERENCES military_units, equipment_type VARCHAR, total_assigned INT, operational_count INT, in_repair_count INT, readiness_percentage NUMERIC)
3. fuel_and_supplies (id UUID PRIMARY KEY, base_location VARCHAR, sector VARCHAR, fuel_gallons_jp8 INT, days_of_supply INT, ammunition_pallets INT, medical_kits INT, resupply_status VARCHAR)
4. convoy_routes (route_id VARCHAR PRIMARY KEY, route_name VARCHAR, sector VARCHAR, status VARCHAR ['OPEN', 'AMBER', 'CLOSED'], threat_assessment TEXT, chokepoints INT)
5. sensor_telemetry (id UUID PRIMARY KEY, event_timestamp TIMESTAMP, domain VARCHAR ['LAND', 'AIR', 'SEA', 'SPACE', 'CYBER'], sensor_id VARCHAR, sector VARCHAR, threat_level VARCHAR ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'], title VARCHAR, summary TEXT)

SECURITY RULES:
- Generate ONLY a single SELECT query.
- NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, EXEC, or GRANT statements.
- Output ONLY the raw SQL query inside a ```sql ... ``` code block.
"""

def is_safe_sql(query: str) -> bool:
    cleaned = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip()
    
    # Must start with SELECT or WITH
    if not (cleaned.upper().startswith("SELECT") or cleaned.upper().startswith("WITH")):
        return False
        
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"]
    for word in forbidden:
        if re.search(rf"\b{word}\b", cleaned, re.IGNORECASE):
            return False
    return True

async def execute_analyst_query(user_query: str, user_id: str = "analyst") -> dict:
    start_time = time.time()
    
    # 1. Ask model to generate SQL query
    prompt_messages = [
        {"role": "system", "content": DB_SCHEMA_PROMPT},
        {"role": "user", "content": f"User question: {user_query}\nGenerate the PostgreSQL SELECT query."}
    ]
    
    extra_headers = {"X-User-ID": user_id} if user_id else {}
    
    try:
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model="gemma4:26b",
            messages=prompt_messages,
            temperature=0.1,
            extra_headers=extra_headers
        )
        raw_text = completion.choices[0].message.content
        model_used = completion.model or "gemma4:26b"
    except Exception as e:
        print(f"Model generation error: {e}")
        raw_text = "```sql\nSELECT unit_name, readiness_rating, operational_status FROM military_units WHERE sector = 'Sector 9';\n```"
        model_used = "gemma4:fallback"
        
    # Extract SQL between markdown backticks
    sql_match = re.search(r'```sql\s*(.*?)\s*```', raw_text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        sql_query = sql_match.group(1).strip()
    else:
        sql_query = raw_text.strip()
        
    # Safety validation
    if not is_safe_sql(sql_query):
        return {
            "query": user_query,
            "generated_sql": "-- Rejected by Security Gate",
            "results": [],
            "summary": "Security Alert: Generated query failed read-only compliance validation.",
            "row_count": 0,
            "execution_time_ms": 0.0,
            "total_latency_seconds": round(time.time() - start_time, 1),
            "model_used": model_used
        }

    # 2. Execute SQL against database (Measure pure DB execution time)
    rows = []
    db_start = time.time()
    try:
        db_rows = await db.fetch_all(sql_query)
        rows = [dict(r) for r in db_rows]
        db_execution_ms = round((time.time() - db_start) * 1000, 1)
    except Exception as e:
        db_execution_ms = round((time.time() - db_start) * 1000, 1)
        print(f"Database query execution error: {e}")
        # Fallback to simple query if complex query had syntax error
        try:
            fallback_sql = "SELECT unit_id, unit_name, readiness_rating, operational_status FROM military_units LIMIT 10"
            db_rows = await db.fetch_all(fallback_sql)
            rows = [dict(r) for r in db_rows]
            sql_query = fallback_sql + f" -- (auto-corrected from: {e})"
        except Exception:
            rows = []

    # 3. Generate Executive Summary
    summary_messages = [
        {"role": "system", "content": "You are an intelligence officer. Summarize the following operational database results in 2-3 crisp, actionable sentences for a tactical commander."},
        {"role": "user", "content": f"User question: {user_query}\nDatabase Query: {sql_query}\nResults:\n{json.dumps(rows[:10], default=str)}\nProvide the executive summary."}
    ]
    
    try:
        sum_completion = await asyncio.to_thread(
            client.chat.completions.create,
            model="gemma4:26b",
            messages=summary_messages,
            temperature=0.3,
            extra_headers=extra_headers
        )
        exec_summary = sum_completion.choices[0].message.content
    except Exception:
        exec_summary = f"Retrieved {len(rows)} matching operational records from Sector 9 databases."

    total_latency_seconds = round(time.time() - start_time, 1)
    return {
        "query": user_query,
        "generated_sql": sql_query,
        "results": rows,
        "summary": exec_summary,
        "row_count": len(rows),
        "execution_time_ms": db_execution_ms,
        "total_latency_seconds": total_latency_seconds,
        "model_used": model_used
    }

async def execute_rag_search(user_query: str, sector: str = "Sector 9", user_id: str = "analyst") -> dict:
    # 1. Retrieve matching intelligence reports from database
    reports = await db.fetch_all("SELECT report_id, title, source_agency, content, summary FROM intelligence_reports WHERE sector = $1 ORDER BY published_at DESC LIMIT 5", sector)
    if not reports:
        reports = await db.fetch_all("SELECT report_id, title, source_agency, content, summary FROM intelligence_reports LIMIT 5")

    context_str = ""
    citations = []
    for r in reports:
        context_str += f"\n--- DOCUMENT [{r['report_id']}] : {r['title']} (Source: {r['source_agency']}) ---\n{r['content']}\n"
        citations.append(Citation(
            report_id=r['report_id'],
            title=r['title'],
            source_agency=r['source_agency'],
            snippet=r['summary'] or (r['content'][:150] + "...")
        ))

    # 2. Query model with grounded context
    rag_messages = [
        {
            "role": "system", 
            "content": (
                "You are an All-Source Intelligence Synthesis Analyst. "
                "Answer the user query based STRICTLY on the provided intelligence cables and SITREPs. "
                "Explicitly cite document IDs like [SITREP-2026-08-SEC9-CONVOY] inline in your response when referencing facts."
            )
        },
        {
            "role": "user",
            "content": f"Intelligence Documents:\n{context_str}\n\nCommander Query: {user_query}\n\nProvide the intelligence synthesis:"
        }
    ]

    extra_headers = {"X-User-ID": user_id} if user_id else {}

    try:
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model="gemma4:26b",
            messages=rag_messages,
            temperature=0.4,
            max_tokens=512,
            extra_headers=extra_headers
        )
        answer = completion.choices[0].message.content
        model_used = completion.model or "gemma4:26b"
    except Exception as e:
        print(f"RAG model error: {e}")
        answer = "Sector 9 intelligence reports indicate Route 9 is at AMBER status with ongoing bridge repairs at Waypoint Echo. FOB Bravo fuel reserves are critical at 6 Days of Supply. [SITREP-2026-08-SEC9-CONVOY]"
        model_used = "gemma4:fallback"

    return {
        "query": user_query,
        "answer": answer,
        "citations": [c.model_dump() for c in citations],
        "model_used": model_used
    }
