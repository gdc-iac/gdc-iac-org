import time
import json
import os
import random
from kafka import KafkaProducer

KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'kafka:9092')
TOPIC = 'orders'

def get_producer():
    while True:
        try:
            producer = KafkaProducer(
                bootstrap_servers=[KAFKA_BROKER],
                value_serializer=lambda x: json.dumps(x).encode('utf-8')
            )
            print("Connected to Kafka")
            return producer
        except Exception as e:
            print(f"Waiting for Kafka: {e}")
            time.sleep(5)

if __name__ == "__main__":
    producer = get_producer()
    
    while True:
        order = {
            'id': random.randint(1000, 9999),
            'item': f"Item-{random.randint(1, 100)}",
            'amount': random.randint(10, 500)
        }
        producer.send(TOPIC, value=order)
        print(f"Sent order: {order}")
        time.sleep(2)
