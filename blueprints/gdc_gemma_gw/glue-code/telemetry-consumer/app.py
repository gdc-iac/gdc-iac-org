"""
app.py - Multi-Domain Telemetry Kafka Consumer
Consumes sensor events from Kafka topic 'multi-domain-telemetry' and normalizes them into PostgreSQL.
"""

import os
import sys
import time
import json
import psycopg2
import threading
from kafka import KafkaConsumer

KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:9092').split(',')
TOPIC_NAME = os.getenv('KAFKA_TOPIC', 'multi-domain-telemetry')
DB_CONN = os.getenv('DB_CONN', "dbname=postgres user=postgres password=password host=postgres-svc.gemma-inference.svc.cluster.local port=5432")

def get_consumer():
    while True:
        try:
            consumer = KafkaConsumer(
                TOPIC_NAME,
                bootstrap_servers=KAFKA_BROKERS,
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                group_id='telemetry-processor-group',
                value_deserializer=lambda x: json.loads(x.decode('utf-8'))
            )
            print(f"[*] Connected to Kafka brokers: {KAFKA_BROKERS} on topic: {TOPIC_NAME}")
            return consumer
        except Exception as e:
            print(f"[!] Waiting for Kafka brokers ({KAFKA_BROKERS}): {e}")
            time.sleep(5)

def get_db_connection():
    while True:
        try:
            conn = psycopg2.connect(DB_CONN)
            return conn
        except Exception as e:
            print(f"[!] Waiting for Database: {e}")
            time.sleep(5)

def health_check():
    while True:
        try:
            with open('/tmp/healthy', 'w') as f:
                f.write('OK')
            with open('/tmp/ready', 'w') as f:
                f.write('OK')
        except Exception as e:
            pass
        time.sleep(5)

def main():
    # Start health check thread for Kubernetes liveness/readiness probes
    t = threading.Thread(target=health_check, daemon=True)
    t.start()

    conn = get_db_connection()
    consumer = get_consumer()

    print(f"[*] Multi-Domain Telemetry Consumer active. Listening for events...")

    for message in consumer:
        try:
            event = message.value
            domain = event.get('domain', 'LAND').upper()
            sensor_id = event.get('sensor_id', 'UNKNOWN-SENSOR')
            sector = event.get('sector', 'Sector 9')
            threat_level = event.get('threat_level', 'LOW').upper()
            lat = event.get('latitude')
            lon = event.get('longitude')
            title = event.get('title', 'Sensor Telemetry Event')
            summary = event.get('summary', '')
            raw_payload = json.dumps(event.get('raw_payload', {}))

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sensor_telemetry (domain, sensor_id, sector, threat_level, latitude, longitude, title, summary, raw_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (domain, sensor_id, sector, threat_level, lat, lon, title, summary, raw_payload))
                conn.commit()

            print(f"[CONSUMED] [{domain}] {title} ({threat_level}) -> Persisted to DB")
        except Exception as e:
            print(f"[ERROR] Failed to process message: {e}")
            # Reconnect DB if connection was dropped
            try:
                conn = get_db_connection()
            except Exception:
                pass

if __name__ == '__main__':
    main()
