#!/bin/bash
# FLUGG runner script
# Usage: flugg_run.sh <input_file> [cycles]
#
# Environment:
#   FLUGG_GDML - Path to GDML geometry file (required)

INPUT_FILE=$1
CYCLES=${2:-5}

if [ -z "$INPUT_FILE" ]; then
    echo "Usage: flugg_run.sh <input_file> [cycles]"
    echo "Environment: FLUGG_GDML must be set to GDML geometry file"
    exit 1
fi

if [ -z "$FLUGG_GDML" ]; then
    echo "ERROR: FLUGG_GDML environment variable not set"
    exit 1
fi

if [ ! -f "$FLUGG_GDML" ]; then
    echo "ERROR: GDML file not found: $FLUGG_GDML"
    exit 1
fi

# Source Geant4 environment
source /opt/geant4/bin/geant4.sh

export FLUPRO=/usr/local/fluka
export FLUFOR=gfortran
export LD_PRELOAD=/opt/flugg/libflugg_gdml.so

echo "FLUGG: Using GDML geometry: $FLUGG_GDML"
echo "FLUGG: Running with $CYCLES cycles"

INPUT_BASE=${INPUT_FILE%.inp}
$FLUPRO/bin/rfluka -N0 -M${CYCLES} ${INPUT_BASE}
