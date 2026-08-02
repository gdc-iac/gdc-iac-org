import os
import time
import json
import psycopg2
from kafka import KafkaConsumer
import threading

# Configuration
KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:9092').split(',')
TOPIC_NAME = 'events'
DB_CONN = os.getenv('DB_CONN', "dbname=events_db user=postgres password=password host=db")

def init_db():
    conn = psycopg2.connect(DB_CONN)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            event_id VARCHAR(50),
            data VARCHAR(255),
            timestamp BIGINT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def get_consumer():
    while True:
        try:
            consumer = KafkaConsumer(
                TOPIC_NAME,
                bootstrap_servers=KAFKA_BROKERS,
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                group_id='event-processor-group',
                value_deserializer=lambda x: json.loads(x.decode('utf-8'))
            )
            print(f"Connected to Kafka brokers: {KAFKA_BROKERS}")
            return consumer
        except Exception as e:
            print(f"Waiting for Kafka: {e}")
            time.sleep(5)

def health_check():
    while True:
        try:
            with open('/tmp/healthy', 'w') as f:
                f.write('OK')
            with open('/tmp/ready', 'w') as f:
                f.write('OK')
        except Exception as e:
            print(f"Health check update failed: {e}")
        time.sleep(5)

if __name__ == "__main__":
    # Start health check thread
    t = threading.Thread(target=health_check)
    t.daemon = True
    t.start()

    # Wait for DB
    print("Waiting for Database...")
    for _ in range(12):
        try:
            init_db()
            print("Database initialized.")
            break
        except Exception as e:
            print(f"DB Init failed, retrying in 5s: {e}")
            time.sleep(5)

    consumer = get_consumer()
    
    print("Starting consumer loop...")
    for message in consumer:
        event = message.value
        print(f"Received Event: {event}")
        
        try:
            conn = psycopg2.connect(DB_CONN)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO events (event_id, data, timestamp) VALUES (%s, %s, %s)",
                (event.get('eventId'), event.get('data'), event.get('timestamp'))
            )
            conn.commit()
            cur.close()
            conn.close()
            print("Saved Event to Database")
        except Exception as e:
            print(f"Error saving to DB: {e}")
