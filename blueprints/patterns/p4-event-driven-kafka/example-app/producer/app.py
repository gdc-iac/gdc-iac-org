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

import time
import json
import os
import random
from kafka import KafkaProducer

KAFKA_BROKERS = (os.environ.get('KAFKA_BROKERS') or os.environ.get('KAFKA_BROKER', 'kafka:9092')).split(',')
TOPIC = os.environ.get('KAFKA_TOPIC', 'events')

def get_producer():
    while True:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS,
                value_serializer=lambda x: json.dumps(x).encode('utf-8')
            )
            print(f"Connected to Kafka brokers: {KAFKA_BROKERS}")
            return producer
        except Exception as e:
            print(f"Waiting for Kafka: {e}")
            time.sleep(5)

if __name__ == "__main__":
    producer = get_producer()
    
    while True:
        seq_id = random.randint(1000, 9999)
        item_name = f"Item-{random.randint(1, 100)}"
        amount = random.randint(10, 500)
        event = {
            'eventId': f"evt-{seq_id}",
            'data': f"{item_name} (amount={amount})",
            'timestamp': int(time.time()),
            'id': seq_id,
            'item': item_name,
            'amount': amount
        }
        producer.send(TOPIC, value=event)
        print(f"Sent event: {event}")
        time.sleep(2)
