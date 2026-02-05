#!/bin/bash
# Script to run FLUKA/FLUGG simulation with external GDML geometry
#
# Usage: ./run_flugg.sh [options]
#
# Options:
#   --gdml FILE        GDML geometry file (required for FLUGG mode)
#   --compact FILE     DD4hep compact XML (will be converted to GDML)
#   --energy GEV       Particle energy in GeV (default: 1500 = 1.5 TeV)
#   --particle TYPE    Particle type: electron, positron, photon (default: electron)
#   --cycles N         Number of cycles (default: 5)
#   --primaries N      Primaries per cycle (default: 1000)
#   --library LIB      Neutron library: JEFF, ENDF, etc. (default: JEFF)
#   --output DIR       Output directory (default: auto-generated)
#
# Examples:
#   ./run_flugg.sh --gdml geometry/detector.gdml --energy 1500
#   ./run_flugg.sh --compact MAIA_v0.xml --energy 1500 --particle electron

set -e

# Default parameters
GDML_FILE=""
COMPACT_FILE=""
ENERGY_GEV=1500  # 1.5 TeV default
PARTICLE="electron"
CYCLES=5
PRIMARIES=1000
NEUTRON_LIB="JEFF"
OUTPUT_DIR=""

# FLUGG Docker image (user needs to build this)
FLUGG_IMAGE="flugg:latest"
# MuColl image for DD4hep conversion
MUCOLL_IMAGE="gitlab-registry.cern.ch/muon-collider/mucoll-deploy/mucoll:2.8-patch2-el9"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --gdml)
            GDML_FILE="$2"
            shift 2
            ;;
        --compact)
            COMPACT_FILE="$2"
            shift 2
            ;;
        --energy)
            ENERGY_GEV="$2"
            shift 2
            ;;
        --particle)
            PARTICLE="$2"
            shift 2
            ;;
        --cycles)
            CYCLES="$2"
            shift 2
            ;;
        --primaries)
            PRIMARIES="$2"
            shift 2
            ;;
        --library)
            NEUTRON_LIB="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            grep "^#" "$0" | grep -v "^#!" | sed 's/^# //'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Map particle names to FLUKA
case "$PARTICLE" in
    electron|e-|e)
        FLUKA_PARTICLE="ELECTRON"
        ;;
    positron|e+)
        FLUKA_PARTICLE="POSITRON"
        ;;
    photon|gamma|g)
        FLUKA_PARTICLE="PHOTON"
        ;;
    muon|mu-|mu)
        FLUKA_PARTICLE="MUON-"
        ;;
    muon+|mu+)
        FLUKA_PARTICLE="MUON+"
        ;;
    *)
        FLUKA_PARTICLE="ELECTRON"
        ;;
esac

echo "============================================"
echo "FLUGG Simulation Runner"
echo "============================================"
echo "Mode: Full detector geometry (GDML/FLUGG)"
echo "Particle: $PARTICLE ($FLUKA_PARTICLE)"
echo "Energy: $ENERGY_GEV GeV"
echo "Cycles: $CYCLES"
echo "Primaries/cycle: $PRIMARIES"
echo "Neutron library: $NEUTRON_LIB"
echo ""

# Handle geometry conversion if needed
if [ -n "$COMPACT_FILE" ]; then
    echo "Converting DD4hep compact XML to GDML..."
    GDML_FILE="geometry/detector_converted.gdml"
    ./convert_geometry.sh "$COMPACT_FILE" "$GDML_FILE"
fi

# Check for GDML file
if [ -z "$GDML_FILE" ]; then
    echo "ERROR: No geometry specified. Use --gdml or --compact"
    exit 1
fi

if [ ! -f "$GDML_FILE" ]; then
    echo "ERROR: GDML file not found: $GDML_FILE"
    exit 1
fi

GDML_FILE_ABS=$(realpath "$GDML_FILE")

# Create timestamped output directory
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
if [ -z "$OUTPUT_DIR" ]; then
    OUTPUT_DIR="output/flugg_${TIMESTAMP}_${ENERGY_GEV}GeV_${PARTICLE}"
fi
mkdir -p "$OUTPUT_DIR"

echo "GDML geometry: $GDML_FILE_ABS"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Save run metadata
cat > "$OUTPUT_DIR/run_info.txt" << EOF
mode=flugg
energy_gev=$ENERGY_GEV
particle=$PARTICLE
fluka_particle=$FLUKA_PARTICLE
cycles=$CYCLES
primaries=$PRIMARIES
timestamp=$TIMESTAMP
gdml_file=$GDML_FILE
neutron_library=$NEUTRON_LIB
EOF

# Generate FLUKA input file for FLUGG
INPUT_FILE="$OUTPUT_DIR/flugg_input.inp"

cat > "$INPUT_FILE" << FLUKA_INPUT
TITLE
FLUGG simulation: ${ENERGY_GEV} GeV ${PARTICLE} in detector geometry
*...+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8
* Use FLUGG geometry from GDML
DEFAULTS                                                              PRECISIO
*
* FLUGG geometry card - tells FLUKA to use Geant4 geometry
* The GDML file path is set via environment variable FLUGG_GDML
GEOBEGIN                                                              FLUGG
GEOEND
*...+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8
* Beam definition: particle at high energy, near z-axis, nearly parallel
* Position: just outside detector (adjust based on geometry)
* Direction: nearly parallel to z-axis (small angle ~1 mrad)
BEAM      ${ENERGY_GEV}.0       0.0       0.0       0.0       0.0       1.0${FLUKA_PARTICLE}
BEAMPOS        0.0       0.1  -5000.0     0.0     0.001       1.0
*...+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8
* Scoring - energy deposition in full geometry
* Large binning to cover detector
USRBIN          10.0    ENERGY      -21.     500.0     500.0    5000.0EDEP-XZ
USRBIN        -500.0    -500.0   -5000.0      100.        1.      200. &
USRBIN          10.0    ENERGY      -22.     500.0     500.0    5000.0EDEP-3D
USRBIN        -500.0    -500.0   -5000.0       50.       50.      100. &
*...+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8
* Track all secondary neutrons
USRBIN          10.0   NEUTRON      -24.     500.0     500.0    5000.0NEUT-XZ
USRBIN        -500.0    -500.0   -5000.0      100.        1.      200. &
*...+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8
RANDOMIZ         1.0
START        ${PRIMARIES}.0
STOP
FLUKA_INPUT

echo "Generated FLUKA input: $INPUT_FILE"

# Check if FLUGG image exists
if ! docker image inspect "$FLUGG_IMAGE" &> /dev/null; then
    echo ""
    echo "WARNING: FLUGG Docker image '$FLUGG_IMAGE' not found."
    echo ""
    echo "To build the FLUGG image, you need:"
    echo "  1. Valid FLUKA license and source code"
    echo "  2. Build using: docker/Dockerfile.flugg"
    echo ""
    echo "Alternatively, if you have FLUGG installed locally, run:"
    echo "  export FLUGG_GDML=$GDML_FILE_ABS"
    echo "  \$FLUPRO/bin/rfluka -N0 -M$CYCLES $(basename $INPUT_FILE .inp)"
    echo ""
    echo "The input file has been generated at: $INPUT_FILE"
    exit 1
fi

echo "Running FLUGG simulation..."

# Run FLUGG in Docker
docker run --rm \
    -v "$(pwd):/data" \
    -v "$GDML_FILE_ABS:/geometry/detector.gdml:ro" \
    -e "FLUGG_GDML=/geometry/detector.gdml" \
    -w "/flugg_work" \
    "$FLUGG_IMAGE" bash -c "
    set -e

    export FLUPRO=/opt/fluka
    export FLUFOR=gfortran
    export FLUGG_GDML=/geometry/detector.gdml

    # Copy input file
    cp /data/$INPUT_FILE .
    INPUT_BASE=\$(basename $INPUT_FILE .inp)

    echo 'Starting FLUGG simulation...'
    \$FLUPRO/bin/rfluka -N0 -M$CYCLES \$INPUT_BASE

    # Process outputs
    echo 'Processing outputs...'

    # Merge USRBIN outputs
    for unit in 21 22 24; do
        if ls \${INPUT_BASE}001_fort.\$unit 1>/dev/null 2>&1; then
            echo \"\${INPUT_BASE}001_fort.\$unit\" > usrbin\${unit}_list.txt
            for i in \$(seq -f '%03g' 2 $CYCLES); do
                if [ -f \"\${INPUT_BASE}\${i}_fort.\$unit\" ]; then
                    echo \"\${INPUT_BASE}\${i}_fort.\$unit\" >> usrbin\${unit}_list.txt
                fi
            done
            echo '' >> usrbin\${unit}_list.txt
            echo \"output_\${unit}.bnn\" >> usrbin\${unit}_list.txt
            \$FLUPRO/bin/usbsuw < usrbin\${unit}_list.txt
        fi
    done

    # Convert to ASCII
    for f in output_*.bnn; do
        [ -f \"\$f\" ] && echo -e \"\$f\n\${f%.bnn}.dat\n\" | \$FLUPRO/bin/usbrea
    done

    # Copy results
    mkdir -p /data/$OUTPUT_DIR
    cp -f *.bnn /data/$OUTPUT_DIR/ 2>/dev/null || true
    cp -f *.dat /data/$OUTPUT_DIR/ 2>/dev/null || true
    cp -f *.out /data/$OUTPUT_DIR/ 2>/dev/null || true
    cp -f *.log /data/$OUTPUT_DIR/ 2>/dev/null || true
    cp -f *.err /data/$OUTPUT_DIR/ 2>/dev/null || true
"

echo ""
echo "============================================"
echo "FLUGG simulation complete!"
echo "Output files are in: $OUTPUT_DIR"
echo "============================================"
