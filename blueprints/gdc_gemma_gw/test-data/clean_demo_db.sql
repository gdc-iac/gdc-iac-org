-- ==============================================================================
-- clean_demo_db.sql
-- Resets the Operation Vanguard Shield Operational Database for Clean Demos
-- Reseeds all force structure, inventory, fuel, routes, and SITREPs.
-- Leaves sensor_telemetry EMPTY (0 rows) so live ingestion can be showcased on camera.
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Ensure Schema Exists
CREATE TABLE IF NOT EXISTS sensor_telemetry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    domain VARCHAR(50) NOT NULL,
    sensor_id VARCHAR(100) NOT NULL,
    sector VARCHAR(50) DEFAULT 'Sector 9',
    threat_level VARCHAR(20) NOT NULL,
    latitude NUMERIC(10, 6),
    longitude NUMERIC(10, 6),
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    raw_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_telemetry_domain ON sensor_telemetry(domain);
CREATE INDEX IF NOT EXISTS idx_telemetry_threat ON sensor_telemetry(threat_level);
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON sensor_telemetry(event_timestamp DESC);

CREATE TABLE IF NOT EXISTS military_units (
    unit_id VARCHAR(50) PRIMARY KEY,
    unit_name VARCHAR(150) NOT NULL,
    branch VARCHAR(50) NOT NULL,
    sector VARCHAR(50) NOT NULL,
    base_location VARCHAR(100) NOT NULL,
    readiness_rating VARCHAR(10) NOT NULL,
    commander VARCHAR(100) NOT NULL,
    personnel_count INT NOT NULL,
    operational_status VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS equipment_inventory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    unit_id VARCHAR(50) REFERENCES military_units(unit_id) ON DELETE CASCADE,
    equipment_type VARCHAR(100) NOT NULL,
    total_assigned INT NOT NULL,
    operational_count INT NOT NULL,
    in_repair_count INT NOT NULL,
    readiness_percentage NUMERIC(5,2) GENERATED ALWAYS AS (ROUND((operational_count::NUMERIC / total_assigned::NUMERIC) * 100, 2)) STORED
);

CREATE TABLE IF NOT EXISTS fuel_and_supplies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    base_location VARCHAR(100) NOT NULL,
    sector VARCHAR(50) NOT NULL,
    fuel_gallons_jp8 INT NOT NULL,
    days_of_supply INT NOT NULL,
    ammunition_pallets INT NOT NULL,
    medical_kits INT NOT NULL,
    resupply_status VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS convoy_routes (
    route_id VARCHAR(50) PRIMARY KEY,
    route_name VARCHAR(100) NOT NULL,
    sector VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    threat_assessment TEXT,
    last_scouted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    chokepoints INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS intelligence_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id VARCHAR(100) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    classification VARCHAR(50) DEFAULT 'UNCLASSIFIED',
    sector VARCHAR(50) DEFAULT 'Sector 9',
    source_agency VARCHAR(100) NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    content TEXT NOT NULL,
    summary TEXT
);

-- ============================================================================
-- 2. Clear All Tables
-- ============================================================================
TRUNCATE sensor_telemetry, military_units, equipment_inventory, fuel_and_supplies, convoy_routes, intelligence_reports CASCADE;

-- ============================================================================
-- 3. Reseed Operational Baseline
-- ============================================================================

-- Military Units
INSERT INTO military_units (unit_id, unit_name, branch, sector, base_location, readiness_rating, commander, personnel_count, operational_status) VALUES
('TF-3-ARMOR', '3rd Combined Arms Battalion', 'Army', 'Sector 9', 'Forward Operating Base (FOB) Alpha', 'C1', 'Lt. Col. Marcus Vance', 780, 'Combat Ready'),
('TF-9-INF', '9th Stryker Brigade Combat Team', 'Army', 'Sector 9', 'FOB Bravo', 'C3', 'Col. Elena Rostova', 1450, 'Marginally Ready - High Vehicle Deadlines'),
('4-MAR-REG', '4th Marine Expeditionary Unit', 'Marines', 'Sector 9', 'Port Campion Staging Area', 'C1', 'Col. James Douglas', 2200, 'Combat Ready'),
('52-FW-SQN', '52nd Fighter Squadron (Vipers)', 'Air Force', 'Sector 9', 'Centurion Air Base', 'C1', 'Lt. Col. Sarah Lin', 320, 'Air Superiority Ready'),
('16-SP-SQN', '16th Space Surveillance Squadron', 'Space Force', 'Sector 9', 'Vanguard Satellite Terminal', 'C1', 'Maj. David Okafor', 95, 'Active Orbital Tracking'),
('CYBER-TF-7', 'Cyber Protection Team 7', 'Cyber Command', 'Sector 9', 'FOB Alpha Command Bunker', 'C2', 'Maj. Kevin Chen', 65, 'Heightened Alert'),
('12-CAV-RECON', '12th Cavalry Reconnaissance Squadron', 'Army', 'Sector 9', 'Observation Post Bravo-4', 'C3', 'Maj. Robert Sterling', 410, 'Marginally Ready - Equipment Deficiencies'),
('588-ENG-BN', '588th Brigade Engineer Battalion', 'Army', 'Sector 9', 'Waypoint Echo Depot', 'C4', 'Lt. Col. Arthur Hayes', 520, 'Not Combat Ready - Demolition Damage');

-- Equipment Inventory
INSERT INTO equipment_inventory (unit_id, equipment_type, total_assigned, operational_count, in_repair_count) VALUES
('TF-3-ARMOR', 'M1A2 SEPv3 Abrams Main Battle Tank', 44, 42, 2),
('TF-3-ARMOR', 'M2A3 Bradley Fighting Vehicle', 30, 28, 2),
('TF-3-ARMOR', 'M109A7 Paladin Self-Propelled Howitzer', 16, 15, 1),
('TF-9-INF', 'Stryker Infantry Carrier Vehicle (ICV)', 80, 52, 28),
('TF-9-INF', 'M-ATV Mine-Resistant Patrol Vehicle', 45, 34, 11),
('4-MAR-REG', 'Amphibious Combat Vehicle (ACV)', 36, 35, 1),
('52-FW-SQN', 'F-16C Fighting Falcon Block 70', 24, 22, 2),
('52-FW-SQN', 'MQ-9 Reaper Block 5 Extended Range', 12, 11, 1),
('16-SP-SQN', 'Mobile High-Gain Phased Array Antenna', 6, 6, 0),
('12-CAV-RECON', 'JLTV Joint Light Tactical Vehicle', 40, 26, 14),
('588-ENG-BN', 'M9 Armored Combat Earthmover (ACE)', 12, 4, 8);

-- Fuel & Supplies
INSERT INTO fuel_and_supplies (base_location, sector, fuel_gallons_jp8, days_of_supply, ammunition_pallets, medical_kits, resupply_status) VALUES
('Forward Operating Base (FOB) Alpha', 'Sector 9', 145000, 18, 420, 950, 'Adequate'),
('FOB Bravo', 'Sector 9', 42000, 6, 110, 280, 'Critical - Resupply Convoy Required'),
('Port Campion Staging Area', 'Sector 9', 380000, 32, 1200, 2500, 'Surplus Reserves'),
('Centurion Air Base', 'Sector 9', 620000, 24, 850, 1400, 'Optimal Readiness');

-- Convoy Routes
INSERT INTO convoy_routes (route_id, route_name, sector, status, threat_assessment, chokepoints) VALUES
('ROUTE-9', 'Supply Route 9 (Vanguard Corridor)', 'Sector 9', 'AMBER', 'Bridge repair underway at Waypoint Echo; suspected recon surveillance drones active.', 3),
('ROUTE-4-NORTH', 'Highway 4 North Bypass', 'Sector 9', 'OPEN', 'Paved commercial highway cleared by EOD teams. Nominal transit speed 65 km/h.', 1),
('ROUTE-7-COASTAL', 'Coastal Logistics Causeway', 'Sector 9', 'OPEN', 'Clear littoral maritime support corridor. Protected by 4th Marine ACV patrols.', 2),
('ROUTE-12-DESERT', 'Desert Ridge Access Path', 'Sector 9', 'CLOSED', 'Flash flooding damage to culverts and unconfirmed IED indicator reports.', 4);

-- Unstructured Intelligence Reports (RAG Corpus)
INSERT INTO intelligence_reports (report_id, title, classification, sector, source_agency, content, summary) VALUES
('SITREP-2026-08-SEC9-CONVOY', 'SITREP: Route 9 Vulnerabilities & Tactical Logistics Status', 'UNCLASSIFIED', 'Sector 9', 'Joint Task Force Vanguard J-2', 
'1. SITUATION: Supply Convoy Route 9 (Vanguard Corridor) remains the primary arterial conduit connecting Port Campion logistics hubs to Forward Operating Base (FOB) Alpha and FOB Bravo. Recent hostile aerial reconnaissance and asymmetric harassment have compromised route security.

2. CHOKEPOINTS:
   a. Waypoint Echo (Bridge Overpass km 42): Combat engineers are repairing structural integrity following explosive detonation. Route is currently restricted to single-lane light vehicles (AMBER status). Full transit capacity estimated in 14 hours.
   b. Defile at Ridge 104: High elevation terrain presents anti-tank guided missile (ATGM) ambush vulnerability.

3. LOGISTICAL IMPACT:
   FOB Bravo has reached critical supply status with only 6 Days of Supply (DOS) for JP-8 aviation/diesel fuel (42,000 gallons remaining). Resupply convoy TF-9-CONVOY-BRAVO cannot proceed until Waypoint Echo bridge is certified for 70-ton military load classification (MLC 70) to support M1A2 Abrams escorts.

4. RECOMMENDATION: Reroute urgent emergency medical and light ammunition convoys via Highway 4 North Bypass. Hold fuel tanker trailers at FOB Alpha until route status is upgraded to GREEN.',
'Route 9 is at AMBER status due to bridge damage at Waypoint Echo. FOB Bravo fuel reserves are critical at 6 DOS (42,000 gal). Emergency resupply recommended via Highway 4 North.'),

('AAR-2026-07-VANGUARD-PHASE1', 'After Action Report: Operation Vanguard Shield Phase 1 Logistics & EW Defense', 'UNCLASSIFIED', 'Sector 9', 'Task Force 3 Armor S-3',
'1. EXECUTIVE SUMMARY: Phase 1 focused on staging the 3rd Combined Arms Battalion at FOB Alpha and hardening the Vanguard Satellite Terminal. Hostile electronic warfare (EW) elements deployed high-power GPS spoofing and UHF SATCOM jamming during unit transit.

2. KEY OBSERVATIONS:
   a. Satellite Communications: 16th Space Surveillance Squadron successfully mitigated jamming by switching to multi-beam phased array beamforming.
   b. Cyber Attack Surface: SCADA fuel distribution networks at FOB Alpha sustained automated port scanning from external IPs. Cyber Protection Team 7 isolated the control network, preventing fuel valve manipulation.
   c. Maintenance: Stryker vehicles with the 9th Brigade sustained 15% breakdown rates on unpaved desert routes, requiring pre-positioning of wheel assembly repair kits.

3. LESSONS LEARNED:
   Future convoy operations must maintain co-located cyber defense elements to safeguard digital vehicle health monitors and automated logistics manifests.',
'Phase 1 validated phased array SATCOM resilience against EW jamming. Cyber Protection Team 7 successfully thwarted SCADA fuel valve sabotage.'),

('INTEL-CABLE-CYBER-SENSOR-CORRELATIONS', 'Intelligence Cable: Cyber-Physical Reconnaissance Correlation in Sector 9', 'UNCLASSIFIED', 'Sector 9', 'Defense Intelligence Agency (Liaison Detachment)',
'SUBJECT: Coordinated Cyber Reconnaissance Preceding Kinetic Harassment

1. ANALYSIS: Recent telemetry from Cyber Protection Team 7 reveals a direct correlation between Modbus SCADA port scans against FOB Alpha fuel pumps and acoustic ground sensor activations along Route 9.
2. ADVERSARY TACTICS: The adversary utilizes cyber probes to gauge fuel availability at forward operating bases. When fuel levels are assessed as depleted or restricted, hostile reconnaissance UAVs are launched to scout alternate highway corridors.
3. DIRECTIVE: Commanders are directed to treat cyber intrusions into infrastructure as leading indicators of imminent ground reconnaissance or ambush activity along adjacent transportation arteries.',
'Cyber probes against fuel SCADA systems are confirmed leading indicators of kinetic ground reconnaissance along Sector 9 supply routes.');

-- NOTE: sensor_telemetry is left deliberately EMPTY (0 rows) so the demo can showcase live ingestion.
