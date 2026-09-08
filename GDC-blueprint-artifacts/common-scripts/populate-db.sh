#!/bin/bash
# ==============================================================================
# populate-db.sh
# Database Population & Seeding Utility for SQL Query & RAG Testing
# Mission: Operation Vanguard Shield
# ==============================================================================
set -e

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
cd "${REPO_ROOT}"

NAMESPACE="${NAMESPACE:-gemma-inference}"
POSTGRES_POD="${POSTGRES_POD:-postgres-0}"

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
    echo -e "${BOLD}${CYAN} 📦 Operational Database Population Utility (Operation Vanguard Shield)${RESET}"
    echo -e "    Namespace:  ${YELLOW}${NAMESPACE}${RESET}"
    echo -e "    Postgres:   ${YELLOW}${POSTGRES_POD}${RESET}"
    echo -e "${BLUE}==============================================================================${RESET}"
}

function show_help() {
    print_header
    echo -e "${BOLD}Usage:${RESET} $0 [OPTION]"
    echo ""
    echo -e "${BOLD}Options:${RESET}"
    echo -e "  ${GREEN}(no args)${RESET}           Full population: Seeds units, equipment, fuel, convoy routes,"
    echo -e "                        unstructured SITREPs, and baseline sensor events."
    echo ""
    echo -e "  ${GREEN}--clean-telemetry${RESET}   Populates all readiness tables & SITREPs, but leaves"
    echo -e "                        sensor telemetry empty (0 rows) for live on-camera streaming."
    echo ""
    echo -e "  ${GREEN}--verify${RESET}            Runs sample SQL queries directly in the CLI to verify data."
    echo ""
    echo -e "  ${GREEN}--help${RESET}              Show this help message."
    echo ""
}

function verify_postgres() {
    if ! kubectl get pod "${POSTGRES_POD}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        echo -e "${RED}[-] Error: Pod '${POSTGRES_POD}' not found in namespace '${NAMESPACE}'.${RESET}"
        echo "    Ensure your GKE cluster credentials and namespace are configured."
        exit 1
    fi
}

function print_status() {
    echo -e "\n${BOLD}[*] Populated Database Record Counts:${RESET}"
    kubectl exec -i "${POSTGRES_POD}" -n "${NAMESPACE}" -- psql -U postgres -d postgres -t -c "
        SELECT '  • military_units:         ' || LPAD(count(*)::text, 4) || ' rows (Force structure & readiness ratings)' FROM military_units
        UNION ALL
        SELECT '  • equipment_inventory:    ' || LPAD(count(*)::text, 4) || ' rows (Abrams, Bradleys, Paladins, Strykers)' FROM equipment_inventory
        UNION ALL
        SELECT '  • fuel_and_supplies:      ' || LPAD(count(*)::text, 4) || ' rows (FOB Alpha, Bravo, Charlie, Delta)' FROM fuel_and_supplies
        UNION ALL
        SELECT '  • convoy_routes:          ' || LPAD(count(*)::text, 4) || ' rows (Route 9, Highway 4, Coastal, Desert)' FROM convoy_routes
        UNION ALL
        SELECT '  • intelligence_reports:   ' || LPAD(count(*)::text, 4) || ' rows (All-source tactical SITREPs)' FROM intelligence_reports
        UNION ALL
        SELECT '  • sensor_telemetry:       ' || LPAD(count(*)::text, 4) || ' rows (Multi-domain Kafka stream)' FROM sensor_telemetry;
    "
    echo ""
}

function print_demo_queries() {
    echo -e "${BOLD}${GREEN}==============================================================================${RESET}"
    echo -e "${BOLD}${GREEN}✅ Database is Fully Populated & Ready for Testing!${RESET}"
    echo -e "${BOLD}${GREEN}==============================================================================${RESET}"
    echo -e "Open the console at: ${CYAN}http://localhost:8081${RESET} (or Workstation Web Preview)"
    echo -e ""
    echo -e "${BOLD}Recommended Queries to Test in the 'Operational Readiness (SQL)' Tab:${RESET}"
    echo -e "  ${CYAN}1.${RESET} ${BOLD}\"List all military units in Sector 9 with combat readiness below C2.\"${RESET}"
    echo -e "     ↳ Returns 3rd Combined Arms Battalion (C1) vs 9th Stryker Brigade (C2)"
    echo -e ""
    echo -e "  ${CYAN}2.${RESET} ${BOLD}\"Check fuel reserves, days of supply, and resupply status at all forward operating bases.\"${RESET}"
    echo -e "     ↳ Highlights FOB Bravo at critical 6 Days of Supply (42,000 gal JP-8)"
    echo -e ""
    echo -e "  ${CYAN}3.${RESET} ${BOLD}\"Show equipment inventory, operational counts, and readiness percentage for TF-3-ARMOR.\"${RESET}"
    echo -e "     ↳ Shows Abrams (95.5%), Bradley (93.3%), and Paladin (93.8%) readiness"
    echo -e ""
    echo -e "  ${CYAN}4.${RESET} ${BOLD}\"List all convoy supply routes, their current status, and chokepoint assessments.\"${RESET}"
    echo -e "     ↳ Identifies Route 9 at AMBER status with bridge damage at Waypoint Echo"
    echo -e ""
    echo -e "${BOLD}Recommended Query for the 'All-Source Intel (RAG)' Tab:${RESET}"
    echo -e "  ${CYAN}5.${RESET} ${BOLD}\"What vulnerabilities were identified for supply convoys along Route 9 in Sector 9?\"${RESET}"
    echo -e "     ↳ Synthesizes paragraph citations from SITREP-2026-08-SEC9-CONVOY"
    echo -e ""
}

function run_cli_verification() {
    verify_postgres
    echo -e "\n${BOLD}[*] Running CLI Verification Query (Force Readiness Sample):${RESET}"
    kubectl exec -i "${POSTGRES_POD}" -n "${NAMESPACE}" -- psql -U postgres -d postgres -c "
        SELECT unit_id, unit_name, base_location, readiness_rating, operational_status 
        FROM military_units 
        ORDER BY readiness_rating ASC;
    "
    
    echo -e "\n${BOLD}[*] Running CLI Verification Query (FOB Fuel Reserves):${RESET}"
    kubectl exec -i "${POSTGRES_POD}" -n "${NAMESPACE}" -- psql -U postgres -d postgres -c "
        SELECT base_location, fuel_gallons_jp8, days_of_supply, resupply_status 
        FROM fuel_and_supplies;
    "
    echo ""
}

# Parse Arguments
MODE="${1:-default}"

case "${MODE}" in
    default|--all)
        print_header
        verify_postgres
        echo -e "[*] Loading complete operational scenario from ${YELLOW}test-data/seed_readiness_db.sql${RESET}..."
        kubectl exec -i "${POSTGRES_POD}" -n "${NAMESPACE}" -- psql -U postgres -d postgres < test-data/seed_readiness_db.sql >/dev/null
        print_status
        print_demo_queries
        ;;
    --clean-telemetry|-c)
        print_header
        verify_postgres
        echo -e "[*] Loading operational readiness tables with ${YELLOW}0 telemetry events${RESET} (for clean recording)..."
        kubectl exec -i "${POSTGRES_POD}" -n "${NAMESPACE}" -- psql -U postgres -d postgres < test-data/clean_demo_db.sql >/dev/null
        print_status
        print_demo_queries
        ;;
    --verify|-v)
        print_header
        run_cli_verification
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
