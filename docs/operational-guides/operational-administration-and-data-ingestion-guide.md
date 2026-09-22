Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Operational Administration & Data Ingestion Guide**
## **AI-Powered Multi-Blueprint Intelligence Synthesis & Decision Support**

> **Document ID:** `OPS-GUIDE-E2E-INTEL-SYNTHESIS`  
> **Version:** 1.0  
> **Classification:** Unclassified // Operational Reference Manual  
> **Applicability:** Google Distributed Cloud air-gapped (GDC-ag) & Connected GCP Emulation  
> **Related Patterns:** Pattern 4 (Kafka), Pattern 6 (RAG Agent), Pattern 7 (Agentic Data Analyst), Pattern 5 (Gemma Gateway), Pattern 10 (Client GUI), Pattern 12 (Keycloak)

---

## **1. Executive Summary & Purpose**

This standalone operational guide details how to transition the **Multi-Blueprint Intelligence Synthesis & Decision Support System** from a laboratory/tutorial deployment into active mission operations.

It delivers step-by-step instructions for:
1. **Live Feed Ingestion:** Hooking real-world sensor protocols (ADS-B, AIS, Cursor-on-Target, SCADA, SATCOM) into the **Apache Kafka (Pattern 4)** stream.
2. **All-Source RAG Population:** Bulk-ingesting, vectorizing, and lifecycle-managing unstructured operational cables and SITREPs in **pgvector (Pattern 6)**.
3. **Database Administration:** Managing, partitioning, securing, and ETL-syncing live readiness records in **PostgreSQL (Pattern 7)**.
4. **Day-2 Runbooks:** Monitoring consumer lag, tuning the Gemma Gateway routing heuristics, managing Keycloak RBAC personas, and disaster recovery.

---

## **2. Hooking Up Live Real-World Sensor Feeds (Pattern 4)**

In operational deployments, the synthetic simulator is replaced by production **Feed Adapters** running on the ingestion perimeter. The adapters translate domain-specific protocols into normalized JSON envelopes published to Kafka.

```
 [ Tactical Field Sensors ]
  ├── Land: Cursor-on-Target (CoT) / Link-16 ──► [ CoT-to-Kafka Adapter ] ────┐
  ├── Air: ADS-B / Mode-S / ASTERIX ────────────► [ ADS-B-to-Kafka Adapter ] ──┤
  ├── Sea: NMEA-0183 / AIVDM (AIS) ────────────► [ AIS-to-Kafka Adapter ] ────┼──► [ Kafka Topic: multi-domain-telemetry ]
  ├── Space: NORAD TLE / CCSDS Downlinks ──────► [ Space-Telemetry Adapter ] ──┤     │
  └── Cyber: Syslog / Suricata / Modbus SCADA ─► [ Logstash / FluentBit ] ────┘     ▼
                                                                             [ Telemetry Consumer Daemon ]
                                                                                   │
                                                                                   ▼
                                                                       [ PostgreSQL: sensor_telemetry ]
```

### **2.1 Standard Telemetry Envelope Specification**
All adapters must serialize sensor records into the following JSON envelope before publishing to Kafka topic `multi-domain-telemetry`:

```json
{
  "event_id": "UUIDv4",
  "event_timestamp": "2026-08-26T14:00:00Z",
  "domain": "LAND | AIR | SEA | SPACE | CYBER",
  "sensor_id": "STRING (e.g. RADAR-S9-042)",
  "sector": "STRING (e.g. Sector 9)",
  "threat_level": "LOW | MEDIUM | HIGH | CRITICAL",
  "latitude": 36.8124,
  "longitude": -115.9123,
  "title": "Short descriptive summary",
  "summary": "Full tactical details, direction, speed, and observations",
  "raw_payload": {
    "protocol_specific_fields": "values"
  }
}
```

---

### **2.2 Live Feed Adapter Implementations**

#### **Adapter A: Air Domain — Real-Time ADS-B Aircraft Tracking**
Reads live ADS-B Mode-S JSON broadcasts from an RTL-SDR receiver or network radar feed (`readsb` / `dump1090`) and streams contacts to Kafka:

```python
#!/usr/bin/env python3
# scripts/adapters/adsb_to_kafka.py
import json, time, urllib.request
from kafka import KafkaProducer

PRODUCER = KafkaProducer(
    bootstrap_servers=["kafka-svc.gemma-inference.svc.cluster.local:9092"],
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)
DUMP1090_URL = "http://radar-receiver.local:8080/data/aircraft.json"

def stream_adsb():
    while True:
        try:
            req = urllib.request.urlopen(DUMP1090_URL, timeout=5)
            data = json.loads(req.read().decode())
            for ac in data.get("aircraft", []):
                if "lat" in ac and "lon" in ac:
                    event = {
                        "domain": "AIR",
                        "sensor_id": f"ADS-B-{ac.get('hex', 'UNKNOWN')}",
                        "sector": "Sector 9",
                        "threat_level": "HIGH" if ac.get("squawk") in ["7500", "7700"] else "LOW",
                        "latitude": ac["lat"],
                        "longitude": ac["lon"],
                        "title": f"Air Track {ac.get('flight', ac.get('hex')).strip()}",
                        "summary": f"Alt: {ac.get('altitude', 'N/A')}ft, Speed: {ac.get('speed', 0)}kts, Squawk: {ac.get('squawk', 'NORM')}",
                        "raw_payload": ac
                    }
                    PRODUCER.send("multi-domain-telemetry", event)
        except Exception as e:
            print(f"[!] ADS-B Feed Warning: {e}")
        time.sleep(2)

if __name__ == "__main__":
    stream_adsb()
```

#### **Adapter B: Maritime Domain — Live AIS Vessel Traffic**
Parses marine VHF AIS NMEA strings from an AIS base station or coastal receiver:

```python
#!/usr/bin/env python3
# scripts/adapters/ais_to_kafka.py
import json, socket
from pyais import decode
from kafka import KafkaProducer

PRODUCER = KafkaProducer(
    bootstrap_servers=["kafka-svc.gemma-inference.svc.cluster.local:9092"],
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

def stream_ais(host="ais-base-station.local", port=10110):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    for line in s.makefile():
        try:
            msg = decode(line.strip())
            decoded = msg.asdict()
            if "lat" in decoded and "lon" in decoded:
                event = {
                    "domain": "SEA",
                    "sensor_id": f"AIS-MMSI-{decoded.get('mmsi')}",
                    "sector": "Sector 9",
                    "threat_level": "LOW",
                    "latitude": decoded["lat"],
                    "longitude": decoded["lon"],
                    "title": f"Vessel Contact MMSI {decoded.get('mmsi')}",
                    "summary": f"Speed: {decoded.get('speed', 0)}kts, Heading: {decoded.get('heading', 0)} deg",
                    "raw_payload": decoded
                }
                PRODUCER.send("multi-domain-telemetry", event)
        except Exception:
            continue

if __name__ == "__main__":
    stream_ais()
```

#### **Adapter C: Cyber Domain — SCADA / Syslog / Suricata IDS Integration**
In production, FluentBit or Logstash forwards IDS/IPS and SCADA alerts directly into Kafka:

```yaml
# /etc/fluent-bit/fluent-bit.conf
[INPUT]
    Name        tail
    Path        /var/log/suricata/eve.json
    Parser      json
    Tag         cyber.alerts

[OUTPUT]
    Name        kafka
    Match       cyber.alerts
    Brokers     kafka-svc.gemma-inference.svc.cluster.local:9092
    Topics      multi-domain-telemetry
    Format      json
```

---

### **2.3 Production Kafka Hardening: Authentication, Retries & DLQ**

1. **Enable TLS and SASL/SCRAM Authentication:**
   In production GDC environments, configure Kafka brokers with SASL/SCRAM authentication to prevent unauthorized signal injection:
   ```yaml
   env:
   - name: KAFKA_SECURITY_INTER_BROKER_PROTOCOL
     value: "SASL_PLAINTEXT"
   - name: KAFKA_SASL_MECHANISM_INTER_BROKER_PROTOCOL
     value: "SCRAM-SHA-512"
   ```
2. **Dead-Letter Queue (DLQ) Configuration:**
   If the consumer encounters malformed JSON or unresolvable coordinates, it diverts the message to `multi-domain-telemetry-dlq` instead of crashing the consumer loop.
3. **Partitioning Strategy:**
   * Partition topic `multi-domain-telemetry` by **Domain** (`LAND`, `AIR`, `SEA`, `SPACE`, `CYBER`) or **Sensor ID**.
   * Run 5 consumer replicas (`replicas: 5`) on `telemetry-consumer` so each partition processes concurrently with zero queue contention.

---

## **3. Populating & Managing the All-Source RAG Repository (Pattern 6)**

The **Resilient RAG Agent (Pattern 6)** ingests unstructured cables, SITREPs, intelligence bulletins, and after-action reports (PDF, Word, Markdown, plain text), generates dense vector embeddings, and stores them in PostgreSQL with `pgvector`.

### **3.1 Object Storage Ingestion Structure**
In production, documents are deposited into a dedicated GDC Object Storage Bucket or Google Cloud Storage bucket:

```
gs://intelligence-debriefs-bucket/
├── incoming/                   # Newly received cables awaiting processing
│   ├── SITREP-2026-08-27-ALPHA.pdf
│   └── INTEL-CABLE-TF-ARMOR.docx
├── processed/                  # Vectorized and active in the RAG search index
│   └── 2026-08/
│       ├── SITREP-2026-08-SEC9-CONVOY.txt
│       └── AAR-VANGUARD-PHASE1.txt
└── quarantine/                 # Failed parsing or corrupted documents
```

---

### **3.2 Automated Document Ingestion Pipeline**

Run the batch ingestion script to process documents from local storage or cloud buckets:

```bash
# Ingest all operational cables from a folder
python scripts/ingest_intelligence_cables.py \
  --input-dir ./unclassified_sitreps/ \
  --sector "Sector 9" \
  --classification "UNCLASSIFIED"
```

#### **How the Ingestion Script Processes Documents (`ingest_intelligence_cables.py`):**
1. **Text Extraction:** Extracts clean text from Markdown, PDF, DOCX, or TXT.
2. **Semantic Chunking:** Splits documents into 500-token chunks with a 50-token sliding window overlap to maintain contextual continuity.
3. **Metadata Extraction:** Extracts Document ID, Source Agency, Timestamp, and Geographic Sector.
4. **Vector Embedding Generation:** Uses the Gemma embedding model (or `text-embedding-004`) to generate 768-dimensional float vectors.
5. **Database Storage:** Inserts chunk text, metadata, and embedding vectors into `intelligence_reports`.

---

### **3.3 Tuning and Maintaining the `pgvector` HNSW Index**

To maintain sub-10 millisecond semantic retrieval latency across millions of intelligence chunks, maintain a Hierarchical Navigable Small World (`HNSW`) vector index in PostgreSQL:

```sql
-- Connect to operational database
-- 1. Create HNSW Cosine Similarity Index
CREATE INDEX IF NOT EXISTS idx_intel_reports_embedding_hnsw 
ON intelligence_reports 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 2. Tune runtime search precision (ef_search)
-- Higher ef_search increases accuracy; lower decreases query latency:
SET hnsw.ef_search = 40;

-- 3. Run Periodic VACUUM ANALYZE to reclaim vector index space
VACUUM ANALYZE intelligence_reports;
```

---

### **3.4 Document Lifecycle Management (Purging & Declassification)**

* **Purge Expired / Superseded Cables:**
  ```sql
  -- Remove intelligence cables older than operational retention threshold (e.g. 180 days)
  DELETE FROM intelligence_reports 
  WHERE report_timestamp < NOW() - INTERVAL '180 days';
  ```
* **Declassification / Re-tagging:**
  ```sql
  UPDATE intelligence_reports 
  SET classification = 'DECLASSIFIED' 
  WHERE report_id = 'SITREP-2026-08-SEC9-CONVOY';
  ```

---

## **4. Operational Database Administration (Pattern 7 SQL Audit)**

The **Agentic Data Analyst (Pattern 7)** enables commanders to query live force readiness, equipment inventories, fuel reserves, and convoy routes.

### **4.1 Production Schema Architecture**
The database consists of 5 operational tables:

| Table Name | Primary Key | Key Columns | Operational Purpose |
| :--- | :--- | :--- | :--- |
| `military_units` | `unit_id` | `unit_name`, `readiness_rating` (`C1`–`C4`), `commander`, `personnel_count` | Force readiness accounting |
| `equipment_inventory` | `id (UUID)` | `unit_id`, `equipment_type`, `total_assigned`, `operational_count`, `readiness_percentage` | Materiel & vehicle availability |
| `fuel_and_supplies` | `id (UUID)` | `base_location`, `fuel_gallons_jp8`, `days_of_supply`, `resupply_status` | Logistics sustainability & supply status |
| `convoy_routes` | `route_id` | `route_name`, `status` (`OPEN`, `AMBER`, `CLOSED`), `threat_assessment`, `chokepoints` | Mobility & route hazard tracking |
| `sensor_telemetry` | `id (UUID)` | `event_timestamp`, `domain`, `sensor_id`, `threat_level`, `latitude`, `longitude` | Multi-domain tactical event log |

---

### **4.2 Bulk Data ETL: Ingesting Enterprise Readiness Records**

To synchronize real-world inventory and unit readiness data from military logistics systems (e.g. GCSS-Army, ERP exports, CSV files):

```bash
# Ingest units CSV into PostgreSQL
psql -h postgres-svc -U postgres -d postgres -c "\copy military_units(unit_id, unit_name, branch, sector, base_location, readiness_rating, commander, personnel_count, operational_status) FROM 'units_export.csv' WITH (FORMAT csv, HEADER true);"

# Ingest supply fuel records
psql -h postgres-svc -U postgres -d postgres -c "\copy fuel_and_supplies(base_location, sector, fuel_gallons_jp8, days_of_supply, ammunition_pallets, medical_kits, resupply_status) FROM 'supplies_export.csv' WITH (FORMAT csv, HEADER true);"
```

---

### **4.3 Least-Privilege Security Roles (Defense-in-Depth)**

To ensure the AI agent can **never mutate, delete, or alter** operational databases, enforce strict database privilege separation:

```sql
-- 1. Create Read-Only Role for the AI Data Analyst Agent
CREATE ROLE db_ro_analyst WITH LOGIN PASSWORD 'StrictlyReadOnlyPassword_2026!';
GRANT CONNECT ON DATABASE postgres TO db_ro_analyst;
GRANT USAGE ON SCHEMA public TO db_ro_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO db_ro_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO db_ro_analyst;

-- Explicitly revoke write, create, and drop permissions
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM db_ro_analyst;

-- 2. Create Ingestion Role for the Kafka Telemetry Consumer
CREATE ROLE db_telemetry_writer WITH LOGIN PASSWORD 'TelemetryWriterPassword_2026!';
GRANT CONNECT ON DATABASE postgres TO db_telemetry_writer;
GRANT USAGE ON SCHEMA public TO db_telemetry_writer;
GRANT INSERT, SELECT ON TABLE sensor_telemetry TO db_telemetry_writer;
```

---

### **4.4 High-Velocity Table Partitioning (`sensor_telemetry`)**

In operational environments receiving millions of sensor signals daily, table bloat causes index degradation. Partition `sensor_telemetry` by week:

```sql
-- Convert sensor_telemetry into a partitioned table
CREATE TABLE sensor_telemetry_partitioned (
    id UUID DEFAULT uuid_generate_v4(),
    event_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    domain VARCHAR(50) NOT NULL,
    sensor_id VARCHAR(100) NOT NULL,
    sector VARCHAR(100) NOT NULL,
    threat_level VARCHAR(20) NOT NULL,
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6),
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    raw_payload JSONB,
    PRIMARY KEY (id, event_timestamp)
) PARTITION BY RANGE (event_timestamp);

-- Create weekly partitions
CREATE TABLE sensor_telemetry_y2026_w35 PARTITION OF sensor_telemetry_partitioned
    FOR VALUES FROM ('2026-08-24 00:00:00+00') TO ('2026-08-31 00:00:00+00');

CREATE TABLE sensor_telemetry_y2026_w36 PARTITION OF sensor_telemetry_partitioned
    FOR VALUES FROM ('2026-08-31 00:00:00+00') TO ('2026-09-07 00:00:00+00');
```

---

## **5. Day-2 Administration, Observability & Runbooks**

### **5.1 Prometheus & Grafana Observability Metrics**
Monitor these key operational signals in your GDC Grafana instance:

| Metric Name | Threshold Alert | Operational Action |
| :--- | :--- | :--- |
| `kafka_consumergroup_lag` | `> 5,000 messages` | Scale consumer replicas: `kubectl scale deployment/telemetry-consumer --replicas=8`. |
| `vllm:num_requests_waiting` | `> 25 queued` | GPU bottleneck. Increase tensor parallelism or scale vLLM replicas across GPU nodes. |
| `vllm:gpu_cache_usage_factor` | `> 95%` | KV cache exhaustion risk. Tune `--max-model-len` or add GPU memory. |
| `pg_stat_activity_count` | `> 180 connections` | Scale PgBouncer pooler or increase PostgreSQL `max_connections`. |
| `gemma_gateway_route_total{model="gemma4:31b"}` | Sustained spike | Confirm high-complexity tactical requests are expected and not caused by prompt loops. |

---

### **5.2 Keycloak Identity & User Administration**

To provision new operators, analysts, or commanders into the system:

```bash
# 1. Access Keycloak Administration via Port-Forward
kubectl port-forward service/keycloak-svc 8080:8080 -n gemma-inference

# 2. Add New Operator via Keycloak CLI inside the container
kubectl exec -it keycloak-0 -n gemma-inference -- \
  /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080/auth \
  --realm master --user admin --password admin

# 3. Create user 'commander_smith' in realm 'gdc-rag-realm'
kubectl exec -it keycloak-0 -n gemma-inference -- \
  /opt/keycloak/bin/kcadm.sh create users -r gdc-rag-realm \
  -s username=commander_smith -s enabled=true

# 4. Set password and assign 'admin' role
kubectl exec -it keycloak-0 -n gemma-inference -- \
  /opt/keycloak/bin/kcadm.sh set-password -r gdc-rag-realm \
  --username commander_smith --new-password "SecurePass2026!"

kubectl exec -it keycloak-0 -n gemma-inference -- \
  /opt/keycloak/bin/kcadm.sh add-roles -r gdc-rag-realm \
  --uusername commander_smith --rolename admin
```

---

### **5.3 Gemma Gateway Routing Classifier Fine-Tuning**

The gateway's heuristic prompt complexity classifier lives in `gateway/proxy/main.py`. In operations, administrators can adjust the routing sensitivity threshold to balance GPU load:

```python
# Adjusting routing sensitivity in gateway/proxy/main.py
HIGH_COMPLEXITY_KEYWORDS = [
    # Tactical reasoning & correlation
    "correlate", "synthesis", "assessment", "intent", "wargame", 
    "coordination", "chokepoint", "contingency", "doctrine",
    # Mathematical and multi-hop indicators
    "calculate", "percentage", "compare", "differential", "vulnerability"
]

# Adjust length threshold: Prompts longer than 60 words escalate to Gemma 4 31B Dense
MAX_WORDS_FOR_LIGHTWEIGHT_ROUTING = 60
```

---

### **5.4 Emergency Troubleshooting Playbooks**

#### **Playbook 1: Kafka Telemetry Consumer Stalled / Lag Accumulating**
* **Symptom:** Sensor signals stop updating in the GUI ticker; Kafka consumer lag exceeds 10,000.
* **Diagnosis:**
  ```bash
  kubectl logs deployment/telemetry-consumer -n gemma-inference --tail=100
  ```
* **Remediation:**
  1. Check PostgreSQL connection pool availability.
  2. If database is responsive, scale consumer replicas:
     ```bash
     kubectl scale deployment/telemetry-consumer --replicas=4 -n gemma-inference
     ```
  3. Restart the consumer deployment to trigger partition rebalancing:
     ```bash
     kubectl rollout restart deployment/telemetry-consumer -n gemma-inference
     ```

#### **Playbook 2: vLLM Out-of-Memory (OOM) or GPU KV Cache Eviction**
* **Symptom:** Inference Gateway returns `502 Bad Gateway` or `504 Gateway Timeout` on 31B queries.
* **Diagnosis:**
  ```bash
  kubectl logs -l app=vllm-31b -n gemma-inference --tail=50 | grep -i "out of memory"
  ```
* **Remediation:**
  1. Reduce maximum sequence length in the vLLM Helm values:
     `--max-model-len 4096` (down from 8192).
  2. Increase GPU memory utilization ratio:
     `--gpu-memory-utilization 0.95`.
  3. Re-apply Helm deployment:
     ```bash
     helm upgrade vllm-gemma-31b blueprints/vllm-gke -f blueprints/vllm-gke/values-gdc.yaml
     ```

#### **Playbook 3: Disaster Recovery — Database Point-In-Time Restore**
* **Procedure in GDC Managed Database:**
  1. Retrieve latest automated snapshot:
     ```bash
     kubectl get backups.database.gdc.goog -n intel-operations
     ```
  2. Restore instance to a new operational database:
     ```yaml
     apiVersion: database.gdc.goog/v1alpha1
     kind: DatabaseRestore
     metadata:
       name: restore-readiness-db
       namespace: intel-operations
     spec:
       backupName: operational-readiness-db-backup-20260826
       targetInstanceName: operational-readiness-db-restored
     ```
