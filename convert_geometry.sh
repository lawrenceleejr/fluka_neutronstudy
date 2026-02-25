#!/bin/bash
# Convert DD4hep compact XML geometry to GDML format
#
# Usage: ./convert_geometry.sh [compact_xml] [output_gdml]
#
# Defaults:
#   compact_xml: MAIA detector from k4geo (muon collider)
#   output_gdml: geometry/detector.gdml
#
# This script uses the MuColl container with DD4hep tools.

set -e

# Default geometry: MAIA from k4geo
DEFAULT_COMPACT="https://raw.githubusercontent.com/key4hep/k4geo/main/MuColl/MAIA/compact/MAIA_v0.xml"
COMPACT_XML=${1:-$DEFAULT_COMPACT}
OUTPUT_GDML=${2:-geometry/detector.gdml}

DOCKER_IMAGE="gitlab-registry.cern.ch/muon-collider/mucoll-deploy/mucoll:2.8-patch2-el9"

echo "============================================"
echo "DD4hep to GDML Geometry Converter"
echo "============================================"
echo "Input: $COMPACT_XML"
echo "Output: $OUTPUT_GDML"
echo "Docker image: $DOCKER_IMAGE"
echo ""

# Create output directory
mkdir -p "$(dirname "$OUTPUT_GDML")"

# Check if input is URL or local file
if [[ "$COMPACT_XML" == http* ]]; then
    echo "Downloading compact XML from URL..."
    COMPACT_BASENAME=$(basename "$COMPACT_XML")
    mkdir -p geometry/compact
    wget -q "$COMPACT_XML" -O "geometry/compact/$COMPACT_BASENAME"

    # Also try to get accompanying files (constants, etc.)
    COMPACT_DIR=$(dirname "$COMPACT_XML")
    for dep in "GlobalConstants.xml" "elements.xml" "materials.xml"; do
        wget -q "$COMPACT_DIR/$dep" -O "geometry/compact/$dep" 2>/dev/null || true
    done

    COMPACT_XML="geometry/compact/$COMPACT_BASENAME"
    echo "Downloaded to: $COMPACT_XML"
fi

# Check if local file exists
if [ ! -f "$COMPACT_XML" ]; then
    echo "ERROR: Compact XML file not found: $COMPACT_XML"
    exit 1
fi

# Get absolute paths
COMPACT_XML_ABS=$(realpath "$COMPACT_XML")
OUTPUT_GDML_ABS=$(realpath "$OUTPUT_GDML")
WORK_DIR=$(dirname "$COMPACT_XML_ABS")

echo "Converting DD4hep compact XML to GDML..."

# Run conversion in MuColl container
docker run --rm \
    -v "$WORK_DIR:/input:ro" \
    -v "$(dirname "$OUTPUT_GDML_ABS"):/output" \
    "$DOCKER_IMAGE" bash -c "
    source /opt/setup_mucoll.sh

    cd /input
    COMPACT_FILE=/input/$(basename $COMPACT_XML_ABS)

    echo 'Running geoConverter...'

    # Try geoConverter first (newer DD4hep)
    if command -v geoConverter &> /dev/null; then
        geoConverter -compact \$COMPACT_FILE -output /output/$(basename $OUTPUT_GDML_ABS)
    # Fallback to dd4hep_GeoConverter
    elif command -v dd4hep_GeoConverter &> /dev/null; then
        dd4hep_GeoConverter -compact \$COMPACT_FILE -output /output/$(basename $OUTPUT_GDML_ABS)
    # Try ddsim --dumpGDML
    else
        echo 'Using ddsim for GDML export...'
        ddsim --compactFile \$COMPACT_FILE --dumpGDML --outputFile /output/$(basename $OUTPUT_GDML_ABS) --numberOfEvents 0 || {
            echo 'Trying alternative method with ROOT...'
            root -l -b -q -e \"
                gSystem->Load(\\\"libDDCore\\\");
                dd4hep::Detector& detector = dd4hep::Detector::getInstance();
                detector.fromCompact(\\\"\$COMPACT_FILE\\\");
                detector.dump();
                detector.world().volume()->Export(\\\"/output/$(basename $OUTPUT_GDML_ABS)\\\");
            \"
        }
    fi

    echo 'Conversion complete.'
"

if [ -f "$OUTPUT_GDML" ]; then
    echo ""
    echo "============================================"
    echo "GDML file created: $OUTPUT_GDML"
    echo "File size: $(du -h "$OUTPUT_GDML" | cut -f1)"
    echo "============================================"
else
    echo "ERROR: GDML conversion failed"
    exit 1
fi
