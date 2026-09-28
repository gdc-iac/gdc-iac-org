#!/usr/bin/env python3
"""
simulate_multidomain_telemetry.py
Multi-Domain Sensor Telemetry Generator for Operation Vanguard Shield.
Simulates high-velocity Land, Air, Sea, Space, and Cyber telemetry events.
Can push events directly to Kafka (p4 topic) or POST to the backend ingest API.
"""

import os
import sys
import time
import json
import random
import argparse
from datetime import datetime, timezone

DOMAINS = ["LAND", "AIR", "SEA", "SPACE", "CYBER"]
THREAT_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

TELEMETRY_TEMPLATES = {
    "LAND": [
        {
            "sensor_id": "SECTOR9-AGS-044",
            "title": "Acoustic Ground Sensor Tripwire",
            "summary": "Heavy tracked vehicle signatures detected moving eastward towards Waypoint Echo on Route 9.",
            "threat_level": "HIGH",
            "lat": 36.8124, "lon": -115.9123,
            "payload": {"frequency_hz": 42.5, "estimated_axles": 6, "speed_kph": 32}
        },
        {
            "sensor_id": "LAND-UAV-SCOUT-02",
            "title": "UAV Visual Route Reconnaissance",
            "summary": "Convoy route Waypoint Echo bridge abutment concrete curing observed. Roadway blocked by repair cranes.",
            "threat_level": "MEDIUM",
            "lat": 36.8190, "lon": -115.9080,
            "payload": {"repair_status": "AMBER", "lane_width_meters": 3.2, "estimated_completion_hours": 12}
        },
        {
            "sensor_id": "LAND-IR-BARRIER-09",
            "title": "Perimeter Infrared Beam Break",
            "summary": "Forward logistics depot sector fence breach attempt detected. Quick reaction force dispatched.",
            "threat_level": "HIGH",
            "lat": 36.8050, "lon": -115.9200,
            "payload": {"zone": "DEPOT_ALPHA_EAST", "dwell_time_sec": 4.5}
        }
    ],
    "AIR": [
        {
            "sensor_id": "RADAR-AWACS-7",
            "title": "Unidentified Medium-Altitude Track",
            "summary": "Intermittent radar return 14,000 ft MSL moving at 180 kts in restricted airspace corridor Alpha.",
            "threat_level": "MEDIUM",
            "lat": 37.1021, "lon": -115.7891,
            "payload": {"squawk": "7700_ALT", "heading_deg": 142, "rcs_sqm": 2.4, "altitude_ft": 14200}
        },
        {
            "sensor_id": "AIR-RF-INTERCEPT-12",
            "title": "Hostile UAV Control Link Telemetry",
            "summary": "Frequency hopping telemetry signal detected on 2.4 GHz industrial band matching adversary drone ground station.",
            "threat_level": "HIGH",
            "lat": 37.0510, "lon": -115.8200,
            "payload": {"freq_mhz": 2435.5, "modulation": "FHSS", "bearing_deg": 215}
        }
    ],
    "SEA": [
        {
            "sensor_id": "AIS-LITTORAL-02",
            "title": "Commercial Cargo Vessel Transit",
            "summary": "Container vessel 'Star Navigator' verified cargo manifest. Safely cleared outer channel into Port Campion.",
            "threat_level": "LOW",
            "lat": 36.4512, "lon": -116.1245,
            "payload": {"mmsi": 367412000, "speed_knots": 14.2, "flag": "US", "draft_meters": 11.5}
        },
        {
            "sensor_id": "SEA-SONAR-BUOY-08",
            "title": "Subsurface Acoustic Anomaly",
            "summary": "Low-frequency cavitation detected along harbor mouth approaches. Unscheduled autonomous underwater vessel suspected.",
            "threat_level": "HIGH",
            "lat": 36.4200, "lon": -116.1500,
            "payload": {"depth_meters": 45, "bearing_deg": 045, "snr_db": 18.2}
        }
    ],
    "SPACE": [
        {
            "sensor_id": "SATCOM-PASS-91",
            "title": "Synthetic Aperture Radar (SAR) Downlink",
            "summary": "Orbital SAR pass confirmed clear terrain and zero stationary vehicles on Highway 4 North Bypass.",
            "threat_level": "LOW",
            "lat": 37.3500, "lon": -116.2000,
            "payload": {"satellite": "USA-314", "resolution_meters": 0.5, "swath_km": 40}
        },
        {
            "sensor_id": "SPACE-OPTICAL-22",
            "title": "Infrared Plume Warning Satellite",
            "summary": "Short-duration thermal flash detected outside combat zone. Telemetry indicates industrial boiler flare, non-hostile.",
            "threat_level": "LOW",
            "lat": 37.4000, "lon": -116.0500,
            "payload": {"satellite": "SBIRS-GEO", "confidence": 0.94, "event_type": "INDUSTRIAL_HEAT"}
        }
    ],
    "CYBER": [
        {
            "sensor_id": "IDS-FIREWALL-FOB-A",
            "title": "Industrial Control System Port Scan",
            "summary": "Coordinated TCP SYN flood against FOB Alpha automated fuel pump distribution SCADA system.",
            "threat_level": "CRITICAL",
            "lat": 36.8100, "lon": -115.9100,
            "payload": {"source_ip": "198.51.100.44", "target_port": 502, "protocol": "Modbus/TCP", "blocked": True}
        },
        {
            "sensor_id": "CYBER-SAT-TERMINAL-01",
            "title": "GPS Spoofing Signal Detected",
            "summary": "Time-sync skew on tactical antenna receiver exceeding 250ns threshold. Anti-jamming filters engaged.",
            "threat_level": "HIGH",
            "lat": 36.8150, "lon": -115.9050,
            "payload": {"c_n0_drop_db": 12.4, "spoofing_probability": 0.88, "mitigation": "BEAMFORMING_ACTIVE"}
        }
    ]
}

def generate_random_event():
    domain = random.choice(DOMAINS)
    template = random.choice(TELEMETRY_TEMPLATES[domain])
    
    event = {
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "sensor_id": template["sensor_id"] + f"-{random.randint(10, 99)}",
        "sector": "Sector 9",
        "threat_level": template["threat_level"],
        "latitude": template["lat"] + round(random.uniform(-0.01, 0.01), 4),
        "longitude": template["lon"] + round(random.uniform(-0.01, 0.01), 4),
        "title": template["title"],
        "summary": template["summary"],
        "raw_payload": template["payload"]
    }
    return event

def send_to_api(api_url, event):
    import urllib.request
    req = urllib.request.Request(
        f"{api_url}/telemetry/ingest",
        data=json.dumps(event).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception as e:
        print(f"Error posting to API: {e}", file=sys.stderr)
        return False

def send_to_kafka(producer, topic, event):
    try:
        producer.send(topic, value=event)
        return True
    except Exception as e:
        print(f"Kafka error: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description="Multi-Domain Sensor Telemetry Generator")
    parser.add_argument("--mode", choices=["stream", "batch"], default="batch", help="Streaming or one-time batch")
    parser.add_argument("--count", type=int, default=10, help="Number of events in batch mode")
    parser.add_argument("--interval", type=float, default=2.0, help="Interval between stream events (seconds)")
    parser.add_argument("--api-url", default="http://localhost:8081/api", help="Backend API base URL")
    parser.add_argument("--kafka-broker", default=None, help="Kafka broker host:port (e.g. localhost:9092)")
    parser.add_argument("--kafka-topic", default="multi-domain-telemetry", help="Kafka topic name")
    args = parser.parse_args()

    kafka_producer = None
    if args.kafka_broker:
        try:
            from kafka import KafkaProducer
            kafka_producer = KafkaProducer(
                bootstrap_servers=[args.kafka_broker],
                value_serializer=lambda v: json.dumps(v).encode("utf-8")
            )
            print(f"[+] Connected to Kafka broker: {args.kafka_broker}")
        except Exception as e:
            print(f"[!] Warning: Could not connect to Kafka: {e}. Falling back to API/stdout.")

    print(f"[*] Starting Multi-Domain Telemetry Generator (Mode: {args.mode})...")

    if args.mode == "batch":
        events = [generate_random_event() for _ in range(args.count)]
        for i, ev in enumerate(events, 1):
            sent = False
            if kafka_producer:
                sent = send_to_kafka(kafka_producer, args.kafka_topic, ev)
            else:
                sent = send_to_api(args.api_url, ev)
            
            status = "SENT" if sent else "PRINTED"
            print(f"[{i}/{args.count}] [{status}] [{ev['domain']}] {ev['title']} ({ev['threat_level']})")
    else:
        print(f"[*] Streaming live events every {args.interval}s. Press Ctrl+C to stop.")
        while True:
            ev = generate_random_event()
            sent = False
            if kafka_producer:
                sent = send_to_kafka(kafka_producer, args.kafka_topic, ev)
            else:
                sent = send_to_api(args.api_url, ev)
            
            status = "SENT" if sent else "PRINTED"
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [{status}] [{ev['domain']}] {ev['title']} ({ev['threat_level']})")
            time.sleep(args.interval)

if __name__ == "__main__":
    main()
