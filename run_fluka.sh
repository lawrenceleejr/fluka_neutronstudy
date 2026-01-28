#!/bin/bash
# Script to run FLUKA neutron simulation in Docker container
# Usage: ./run_fluka.sh [number_of_cycles] [energy_MeV]

set -e

CYCLES=${1:-5}
ENERGY_MEV=${2:-1}  # Default 1 MeV
INPUT_FILE="neutron_bpe.inp"
DOCKER_IMAGE="fluka:ggi"
WORK_DIR="/fluka_work"

# Convert MeV to GeV for FLUKA
ENERGY_GEV=$(echo "scale=6; $ENERGY_MEV / 1000" | bc)

# Create timestamped output directory with energy info
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_DIR="output/${TIMESTAMP}_${ENERGY_MEV}MeV"
mkdir -p "$OUTPUT_DIR"

echo "============================================"
echo "FLUKA Neutron Capture Simulation"
echo "============================================"
echo "Input file: $INPUT_FILE"
echo "Cycles: $CYCLES"
echo "Neutron energy: $ENERGY_MEV MeV ($ENERGY_GEV GeV)"
echo "Output directory: $OUTPUT_DIR"
echo "Docker image: $DOCKER_IMAGE"
echo ""

# Save run metadata
cat > "$OUTPUT_DIR/run_info.txt" << EOF
energy_mev=$ENERGY_MEV
energy_gev=$ENERGY_GEV
cycles=$CYCLES
timestamp=$TIMESTAMP
input_file=$INPUT_FILE
EOF

# Run FLUKA simulation in Docker
echo "Starting FLUKA simulation..."
docker run --rm -v "$(pwd):/data" -w "$WORK_DIR" "$DOCKER_IMAGE" bash -c '
    set -e

    # Install required packages if not present
    if ! command -v gfortran &> /dev/null || ! command -v wget &> /dev/null; then
        echo "Installing required packages..."
        apt-get update -qq && apt-get install -y -qq gfortran wget
    fi

    # FLUKA installation path
    FLUPRO=/usr/local/fluka
    export FLUPRO
    export FLUFOR=gfortran

    # Download neutron data if not present
    NEUTRON_DATA_DIR="$FLUPRO/data/neutron"
    if [ ! -d "$NEUTRON_DATA_DIR" ]; then
        echo "Downloading FLUKA pointwise neutron data libraries..."
        echo "This may take a few minutes on first run..."
        mkdir -p "$FLUPRO/data"
        cd "$FLUPRO/data"

        # Download from FLUKA website
        wget -q --show-progress https://fluka.cern/download/neutron-data-libraries/endf8r0_xsec_fluka4-4.4_20241021.tar.xz -O neutron_data.tar.xz || {
            echo "Failed to download neutron data. Trying alternative URL..."
            wget -q --show-progress https://fluka.cern/download/latest/data/endf8r0_xsec.tar.xz -O neutron_data.tar.xz || {
                echo "ERROR: Could not download neutron data libraries."
                echo "Please download manually from: https://fluka.cern/download/neutron-data-libraries"
                exit 1
            }
        }

        echo "Extracting neutron data..."
        tar -xf neutron_data.tar.xz
        rm neutron_data.tar.xz

        # Find and rename the extracted directory to "neutron"
        EXTRACTED_DIR=$(ls -d */ 2>/dev/null | head -1)
        if [ -n "$EXTRACTED_DIR" ] && [ ! -d "neutron" ]; then
            mv "$EXTRACTED_DIR" neutron
        fi

        echo "Neutron data installed successfully."
    else
        echo "Neutron data already present."
    fi

    INPUT_FILE="neutron_bpe.inp"
    INPUT_BASE="${INPUT_FILE%.inp}"
    CYCLES='"$CYCLES"'
    ENERGY_GEV='"$ENERGY_GEV"'
    ENERGY_MEV='"$ENERGY_MEV"'
    OUTPUT_DIR='"$OUTPUT_DIR"'

    # Copy input file to working directory
    mkdir -p /fluka_work
    cd /fluka_work
    cp /data/$INPUT_FILE .

    # Update neutron energy in input file
    # BEAM card format: BEAM energy ... NEUTRON (energy in GeV)
    # Use printf to format the energy value properly for FLUKA fixed format
    ENERGY_STR=$(printf "%10.4E" $ENERGY_GEV)
    sed -i "s/^BEAM .*/BEAM      $ENERGY_STR       0.0       0.0       0.0       0.0       1.0NEUTRON/" $INPUT_FILE
    echo "Set neutron energy to $ENERGY_MEV MeV ($ENERGY_GEV GeV)"

    echo "FLUKA path: $FLUPRO"
    echo "Running simulation with rfluka..."

    # Run FLUKA using rfluka script
    # -N0 means start from cycle 0, -M is number of cycles
    $FLUPRO/bin/rfluka -N0 -M${CYCLES} ${INPUT_BASE} || {
        echo ""
        echo "=== FLUKA run failed. Checking logs ==="
        echo "--- .out file ---"
        cat ${INPUT_BASE}001.out 2>/dev/null | tail -100 || echo "No .out file"
        echo "--- .err file ---"
        cat ${INPUT_BASE}001.err 2>/dev/null || echo "No .err file"
        echo "--- .log file ---"
        cat ${INPUT_BASE}001.log 2>/dev/null || echo "No .log file"
        # Copy whatever we have
        mkdir -p /data/$OUTPUT_DIR
        cp -f *.out /data/$OUTPUT_DIR/ 2>/dev/null || true
        cp -f *.err /data/$OUTPUT_DIR/ 2>/dev/null || true
        cp -f *.log /data/$OUTPUT_DIR/ 2>/dev/null || true
        exit 1
    }

    echo ""
    echo "Simulation complete. Processing output..."

    # Find and process USRBIN output files
    echo "Merging USRBIN output files..."

    # For unit 21 (XZ projection)
    if ls ${INPUT_BASE}001_fort.21 1>/dev/null 2>&1; then
        echo "${INPUT_BASE}001_fort.21" > usrbin21_list.txt
        for i in $(seq -f "%03g" 2 $CYCLES); do
            if [ -f "${INPUT_BASE}${i}_fort.21" ]; then
                echo "${INPUT_BASE}${i}_fort.21" >> usrbin21_list.txt
            fi
        done
        echo "" >> usrbin21_list.txt
        echo "usrbin21_list.txt_sum" >> usrbin21_list.txt
        cat usrbin21_list.txt

        $FLUPRO/bin/usbsuw < usrbin21_list.txt
        if [ -f usrbin21_list.txt_sum ]; then
            mv usrbin21_list.txt_sum edep_xz.bnn
        fi
        echo "done 21"
    fi

    # For unit 22 (3D)
    if ls ${INPUT_BASE}001_fort.22 1>/dev/null 2>&1; then
        ls ${INPUT_BASE}001_fort.22
        echo "${INPUT_BASE}001_fort.22" > usrbin22_list.txt
        for i in $(seq -f "%03g" 2 $CYCLES); do
            if [ -f "${INPUT_BASE}${i}_fort.22" ]; then
                echo "${INPUT_BASE}${i}_fort.22" >> usrbin22_list.txt
            fi
        done
        cat usrbin22_list.txt

        echo "" >> usrbin22_list.txt
        echo "usrbin22_list.txt_sum" >> usrbin22_list.txt

        $FLUPRO/bin/usbsuw < usrbin22_list.txt
        if [ -f usrbin22_list.txt_sum ]; then
            mv usrbin22_list.txt_sum edep_3d.bnn
        fi
    fi
    echo "done 22"

    # Convert binary USRBIN to ASCII using usbrea
    echo "Converting to ASCII format..."

    if [ -f edep_xz.bnn ]; then
        echo -e "edep_xz.bnn\nedep_xz.dat\n" | $FLUPRO/bin/usbrea
    fi

    if [ -f edep_3d.bnn ]; then
        echo -e "edep_3d.bnn\nedep_3d.dat\n" | $FLUPRO/bin/usbrea
    fi

    # Copy all outputs back to data directory
    mkdir -p /data/$OUTPUT_DIR
    cp -f *.bnn /data/$OUTPUT_DIR/ 2>/dev/null || true
    cp -f *.dat /data/$OUTPUT_DIR/ 2>/dev/null || true
    cp -f *.out /data/$OUTPUT_DIR/ 2>/dev/null || true
    cp -f *.log /data/$OUTPUT_DIR/ 2>/dev/null || true
    cp -f *.err /data/$OUTPUT_DIR/ 2>/dev/null || true

    echo ""
    echo "Output files copied to /data/$OUTPUT_DIR/"
    ls -la /data/$OUTPUT_DIR/
'

# Create/update symlink to latest output
rm -f output/latest
ln -s "$(basename "$OUTPUT_DIR")" output/latest

echo ""
echo "============================================"
echo "Simulation finished!"
echo "Output files are in: $OUTPUT_DIR"
echo "Symlink created: output/latest -> $(basename "$OUTPUT_DIR")"
echo "Run: python3 plot_edep.py to visualize results"
echo "============================================"
