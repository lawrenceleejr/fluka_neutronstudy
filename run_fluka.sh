#!/bin/bash
# Script to run FLUKA neutron simulation in Docker container
# Usage: ./run_fluka.sh [number_of_cycles]

set -e

CYCLES=${1:-5}
INPUT_FILE="neutron_bpe.inp"
DOCKER_IMAGE="fluka:ggi"
WORK_DIR="/fluka_work"

echo "============================================"
echo "FLUKA Neutron Capture Simulation"
echo "============================================"
echo "Input file: $INPUT_FILE"
echo "Cycles: $CYCLES"
echo "Docker image: $DOCKER_IMAGE"
echo ""

# Create output directory
mkdir -p output

# Run FLUKA simulation in Docker
echo "Starting FLUKA simulation..."
docker run --rm -v "$(pwd):/data" -w "$WORK_DIR" "$DOCKER_IMAGE" bash -c '
    set -e

    # FLUKA installation path
    FLUPRO=/opt/fluka
    export FLUPRO
    export FLUFOR=gfortran

    INPUT_FILE="neutron_bpe.inp"
    INPUT_BASE="${INPUT_FILE%.inp}"
    CYCLES='"$CYCLES"'

    # Copy input file to working directory
    mkdir -p /fluka_work
    cd /fluka_work
    cp /data/$INPUT_FILE .

    echo "FLUKA path: $FLUPRO"
    echo "Running simulation with rfluka..."

    # Run FLUKA using rfluka script
    # -N0 means start from cycle 0, -M is number of cycles
    $FLUPRO/flutil/rfluka -N0 -M${CYCLES} ${INPUT_BASE}

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
        cat usrbin21_list.txt

        $FLUPRO/flutil/usbsuw < usrbin21_list.txt
        if [ -f usrbin21_list.txt_sum ]; then
            mv usrbin21_list.txt_sum edep_xz.bnn
        fi
    fi

    # For unit 22 (3D)
    if ls ${INPUT_BASE}001_fort.22 1>/dev/null 2>&1; then
        echo "${INPUT_BASE}001_fort.22" > usrbin22_list.txt
        for i in $(seq -f "%03g" 2 $CYCLES); do
            if [ -f "${INPUT_BASE}${i}_fort.22" ]; then
                echo "${INPUT_BASE}${i}_fort.22" >> usrbin22_list.txt
            fi
        done

        $FLUPRO/flutil/usbsuw < usrbin22_list.txt
        if [ -f usrbin22_list.txt_sum ]; then
            mv usrbin22_list.txt_sum edep_3d.bnn
        fi
    fi

    # Convert binary USRBIN to ASCII using usbrea
    echo "Converting to ASCII format..."

    if [ -f edep_xz.bnn ]; then
        echo -e "edep_xz.bnn\nedep_xz.dat\n" | $FLUPRO/flutil/usbrea
    fi

    if [ -f edep_3d.bnn ]; then
        echo -e "edep_3d.bnn\nedep_3d.dat\n" | $FLUPRO/flutil/usbrea
    fi

    # Copy all outputs back to data directory
    mkdir -p /data/output
    cp -f *.bnn /data/output/ 2>/dev/null || true
    cp -f *.dat /data/output/ 2>/dev/null || true
    cp -f *.out /data/output/ 2>/dev/null || true
    cp -f *.log /data/output/ 2>/dev/null || true
    cp -f *_fort.* /data/output/ 2>/dev/null || true
    cp -f *.err /data/output/ 2>/dev/null || true

    echo ""
    echo "Output files copied to /data/output/"
    ls -la /data/output/
'

echo ""
echo "============================================"
echo "Simulation finished!"
echo "Output files are in ./output/"
echo "Run: python3 plot_edep.py to visualize results"
echo "============================================"
