#!/bin/bash
# ==============================================================================
# clean-db.sh
# Database Cleanup & Demo Preparation Utility
# Mission: Operation Vanguard Shield
# ==============================================================================
set -e

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
cd "${REPO_ROOT}"

NAMESPACE="${NAMESPACE:-gemma-inference}"
POSTGRES_POD="${POSTGRES_POD:-postgres-0}"
KAFKA_POD="${KAFKA_POD:-kafka-0}"

# Text formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
RESET="\033[0m"

function print_header() {
    echo -e "${BLUE}==============================================================================${RESET}"
    echo -e "${BOLD}${CYAN} 🧹 Database Cleanup & Demo Reset Utility (Operation Vanguard Shield)${RESET}"
    echo -e "    Namespace:  ${YELLOW}${NAMESPACE}${RESET}"
    echo -e "    Postgres:   ${YELLOW}${POSTGRES_POD}${RESET}"
    echo -e "${BLUE}==============================================================================${RESET}"
}

function show_help() {
    print_header
    echo -e "${BOLD}Usage:${RESET} $0 [OPTION]"
    echo ""
    echo -e "${BOLD}Options:${RESET}"
    echo -e "  ${GREEN}--telemetry${RESET}     (Default) Wipe ONLY sensor telemetry events (0 rows)."
    echo -e "                  Leaves all military units, fuel, and SITREPs intact."
    echo -e "                  Resets Kafka consumer group offset so stale pings are discarded."
    echo -e "                  ${YELLOW}Recommended right before clicking 'Record' on your demo!${RESET}"
    echo ""
    echo -e "  ${GREEN}--full${RESET}          Full demo reset: Reseeds all readiness, units, fuel, and SITREPs,"
    echo -e "                  but leaves sensor telemetry at 0 rows for live ingestion."
    echo ""
    echo -e "  ${GREEN}--seed-all${RESET}      Complete reset AND load the 6 initial baseline sensor events."
    echo ""
    echo -e "  ${GREEN}--status${RESET}        Display current row counts across all operational database tables."
    echo ""
    echo -e "  ${GREEN}--help${RESET}          Show this help message."
    echo ""
}

function verify_postgres() {
    if ! kubectl get pod "${POSTGRES_POD}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        echo -e "${RED}[-] Error: Pod '${POSTGRES_POD}' not found in namespace '${NAMESPACE}'.${RESET}"
        echo "    Ensure your GKE cluster credentials and namespace are configured."
        exit 1
    fi
}

function show_status() {
    verify_postgres
    echo -e "\n${BOLD}[*] Current Operational Database Row Counts:${RESET}"
    kubectl exec -i "${POSTGRES_POD}" -n "${NAMESPACE}" -- psql -U postgres -d postgres -t -c "
        SELECT '  • sensor_telemetry:       ' || LPAD(count(*)::text, 4) || ' rows (Kafka stream buffer)' FROM sensor_telemetry
        UNION ALL
        SELECT '  • military_units:         ' || LPAD(count(*)::text, 4) || ' rows (Forces in Sector 9)' FROM military_units
        UNION ALL
        SELECT '  • equipment_inventory:    ' || LPAD(count(*)::text, 4) || ' rows (Vehicles & Armor)' FROM equipment_inventory
        UNION ALL
        SELECT '  • fuel_and_supplies:      ' || LPAD(count(*)::text, 4) || ' rows (FOB supply reserves)' FROM fuel_and_supplies
        UNION ALL
        SELECT '  • convoy_routes:          ' || LPAD(count(*)::text, 4) || ' rows (Corridors & Chokepoints)' FROM convoy_routes
        UNION ALL
        SELECT '  • intelligence_reports:   ' || LPAD(count(*)::text, 4) || ' rows (All-Source SITREPs)' FROM intelligence_reports;
    "
    echo ""
}

function reset_kafka_offset() {
    if kubectl get pod "${KAFKA_POD}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        echo -e "[*] Resetting Kafka consumer group '${CYAN}telemetry-processor-group${RESET}' to latest offset..."
        kubectl exec -i "${KAFKA_POD}" -n "${NAMESPACE}" -- \
            /opt/kafka/bin/kafka-consumer-groups.sh \
            --bootstrap-server localhost:9092 \
            --group telemetry-processor-group \
            --reset-offsets --to-latest --execute \
            --topic multi-domain-telemetry >/dev/null 2>&1 || true
        echo -e "${GREEN}[+] Kafka consumer offsets reset. Stale messages will not be re-ingested.${RESET}"
    fi
}

# Parse Arguments
MODE="${1:---telemetry}"

case "${MODE}" in
    --telemetry|-t)
        print_header
        verify_postgres
        echo -e "[*] Cleaning sensor telemetry table (${YELLOW}sensor_telemetry${RESET})..."
        kubectl exec -i "${POSTGRES_POD}" -n "${NAMESPACE}" -- psql -U postgres -d postgres -c "
            TRUNCATE TABLE sensor_telemetry;
        " >/dev/null
        reset_kafka_offset
        echo -e "${GREEN}[+] Success: sensor_telemetry wiped clean (0 events).${RESET}"
        show_status
        echo -e "${BOLD}${GREEN}🎬 Demo Ready! The Tactical Feeds ticker is now empty.${RESET}"
        echo -e "   Click ${BOLD}'⚡ Ingest Sensor Pings'${RESET} in the UI to watch events stream in live on camera!\n"
        ;;
    --full|-f)
        print_header
        verify_postgres
        echo -e "[*] Performing full operational database reset with ${YELLOW}0 telemetry events${RESET}..."
        kubectl exec -i "${POSTGRES_POD}" -n "${NAMESPACE}" -- psql -U postgres -d postgres < test-data/clean_demo_db.sql >/dev/null
        reset_kafka_offset
        echo -e "${GREEN}[+] Success: All operational tables re-seeded to clean baseline.${RESET}"
        show_status
        echo -e "${BOLD}${GREEN}🎬 Demo Ready! Operational readiness & SITREPs reset; sensor ticker empty.${RESET}\n"
        ;;
    --seed-all|-s)
        print_header
        verify_postgres
        echo -e "[*] Performing full database reset and loading ${YELLOW}all 6 baseline telemetry events${RESET}..."
        kubectl exec -i "${POSTGRES_POD}" -n "${NAMESPACE}" -- psql -U postgres -d postgres < test-data/seed_readiness_db.sql >/dev/null
        reset_kafka_offset
        echo -e "${GREEN}[+] Success: All tables re-seeded including baseline sensor events.${RESET}"
        show_status
        ;;
    --status)
        print_header
        show_status
        ;;
    --help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}[-] Unknown option: ${MODE}${RESET}"
        show_help
        exit 1
        ;;
esac
