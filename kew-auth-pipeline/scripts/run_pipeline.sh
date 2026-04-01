#!/usr/bin/env bash
# =============================================================================
# Kew Botanical Extract Authentication Pipeline
# Royal Botanic Gardens, Kew
#
# Usage: ./run_pipeline.sh <mzml_file> <bi_number> <manufacturer> <product_code> \
#            <commercial_name> <claimed_species> <plant_genus> [reference_mzml]
# =============================================================================

set -euo pipefail

# Colour codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No colour

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

log_step() {
    echo -e "${CYAN}[$(timestamp)]${NC} ${GREEN}$1${NC}"
}

log_error() {
    echo -e "${CYAN}[$(timestamp)]${NC} ${RED}ERROR: $1${NC}"
}

log_warn() {
    echo -e "${CYAN}[$(timestamp)]${NC} ${YELLOW}WARNING: $1${NC}"
}

# Check arguments
if [ $# -lt 7 ]; then
    echo "Usage: $0 <mzml_file> <bi_number> <manufacturer> <product_code> <commercial_name> <claimed_species> <plant_genus> [reference_mzml]"
    echo ""
    echo "Arguments:"
    echo "  mzml_file        Path to input .mzML file"
    echo "  bi_number        BI number for the sample"
    echo "  manufacturer     Manufacturer name"
    echo "  product_code     Product code"
    echo "  commercial_name  Commercial name of the product"
    echo "  claimed_species  Claimed plant species (e.g., 'Curcuma longa')"
    echo "  plant_genus      Plant genus (e.g., 'Curcuma')"
    echo "  reference_mzml   (Optional) Path to authenticated reference mzML/MGF"
    echo ""
    echo "Example:"
    echo "  $0 data/input/sample.mzML 2024001 \"Herbal Co\" HC-001 \"Turmeric Extract\" \"Curcuma longa\" Curcuma"
    exit 1
fi

MZML_FILE="$1"
BI_NUMBER="$2"
MANUFACTURER="$3"
PRODUCT_CODE="$4"
COMMERCIAL_NAME="$5"
CLAIMED_SPECIES="$6"
PLANT_GENUS="$7"
REFERENCE_MZML="${8:-}"

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${PROJECT_DIR}/data/output"
REFERENCE_DIR="${PROJECT_DIR}/data/reference"
LIBRARIES_DIR="${PROJECT_DIR}/libraries"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo ""
echo "============================================================"
echo "  ROYAL BOTANIC GARDENS, KEW"
echo "  Botanical Extract Authentication Pipeline"
echo "============================================================"
echo ""
echo "  Sample:     BI-${BI_NUMBER}"
echo "  Species:    ${CLAIMED_SPECIES}"
echo "  Genus:      ${PLANT_GENUS}"
echo "  Input:      ${MZML_FILE}"
echo "  Reference:  ${REFERENCE_MZML:-None}"
echo "  Output:     ${OUTPUT_DIR}"
echo ""
echo "============================================================"
echo ""

# Copy reference file to data/reference/ if provided
if [ -n "$REFERENCE_MZML" ] && [ -f "$REFERENCE_MZML" ]; then
    log_step "Copying reference file to data/reference/"
    mkdir -p "$REFERENCE_DIR"
    cp "$REFERENCE_MZML" "$REFERENCE_DIR/"
fi

# ---- STEP 0: Reference Handler ----
log_step "STEP 0: Reference Handler"
if python3 "${SCRIPT_DIR}/00_reference_handler.py" "" "$REFERENCE_DIR" "$OUTPUT_DIR"; then
    log_step "Step 0 complete."
else
    log_error "Step 0 failed."
    exit 1
fi
echo ""

# ---- STEP 1: mzML Processing ----
log_step "STEP 1: mzML Processing (MZmine 3)"
if python3 "${SCRIPT_DIR}/01_process_mzml.py" "$MZML_FILE" "$OUTPUT_DIR"; then
    log_step "Step 1 complete."
else
    log_error "Step 1 failed. Cannot proceed without feature detection."
    exit 1
fi
echo ""

MGF_FILE="${OUTPUT_DIR}/gnps_export.mgf"

# ---- Re-run Step 0 with query MGF if reference exists ----
CONFIG_FILE="${OUTPUT_DIR}/pipeline_config.json"
if [ -f "$CONFIG_FILE" ]; then
    HAS_REF=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['has_reference'])" 2>/dev/null || echo "False")
    if [ "$HAS_REF" = "True" ] && [ -f "$MGF_FILE" ]; then
        log_step "Re-running Step 0 with query MGF for reference comparison..."
        python3 "${SCRIPT_DIR}/00_reference_handler.py" "$MGF_FILE" "$REFERENCE_DIR" "$OUTPUT_DIR"
    fi
fi
echo ""

# ---- STEP 2: Spectral Annotation ----
log_step "STEP 2: Spectral Annotation (matchms)"
if python3 "${SCRIPT_DIR}/02_annotate_matchms.py" "$MGF_FILE" "$LIBRARIES_DIR" "$OUTPUT_DIR"; then
    log_step "Step 2 complete."
else
    log_error "Step 2 failed."
    exit 1
fi
echo ""

# ---- STEP 3: SIRIUS Annotation ----
log_step "STEP 3: SIRIUS Annotation"
if python3 "${SCRIPT_DIR}/03_sirius_runner.py" "$MGF_FILE" "$OUTPUT_DIR"; then
    log_step "Step 3 complete."
else
    log_warn "Step 3 had issues (SIRIUS may not be installed). Continuing..."
fi
echo ""

# ---- STEP 4: Literature Search ----
log_step "STEP 4: Literature Search & Verification"
if python3 "${SCRIPT_DIR}/04_literature_search.py" "$OUTPUT_DIR" "$PLANT_GENUS" "$CLAIMED_SPECIES"; then
    log_step "Step 4 complete."
else
    log_error "Step 4 failed."
    exit 1
fi
echo ""

# ---- STEP 5: Report Generation ----
log_step "STEP 5: Report Generation"
if python3 "${SCRIPT_DIR}/05_generate_report.py" "$BI_NUMBER" "$MANUFACTURER" "$PRODUCT_CODE" "$COMMERCIAL_NAME" "$CLAIMED_SPECIES" "$OUTPUT_DIR"; then
    log_step "Step 5 complete."
else
    log_error "Step 5 failed."
    exit 1
fi
echo ""

# ---- DONE ----
echo ""
echo "============================================================"
echo -e "  ${GREEN}PIPELINE COMPLETE${NC}"
echo "============================================================"
echo ""
echo "  Output directory: ${OUTPUT_DIR}"
echo ""
echo "  Files generated:"
ls -la "$OUTPUT_DIR"/*.csv "$OUTPUT_DIR"/*.docx "$OUTPUT_DIR"/*.json "$OUTPUT_DIR"/*.txt 2>/dev/null | awk '{print "    " $NF " (" $5 " bytes)"}'
echo ""

# Print verdict
if [ -f "${OUTPUT_DIR}/verdict.txt" ]; then
    echo "============================================================"
    cat "${OUTPUT_DIR}/verdict.txt"
    echo "============================================================"
fi
