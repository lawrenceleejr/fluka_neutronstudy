#!/bin/bash
# Simplified script to run FLUKA in Docker container
# This runs interactively inside the container for debugging

DOCKER_IMAGE="fluka:ggi"

echo "Starting interactive FLUKA container..."
echo "Run these commands inside the container:"
echo ""
echo "  cd /fluka_work"
echo "  cp /data/neutron_bpe.inp ."
echo "  \$FLUPRO/flutil/rfluka -N0 -M1 neutron_bpe"
echo "  # Then process output with usbsuw and usbrea"
echo ""

docker run -it --rm \
    -v "$(pwd):/data" \
    -w "/fluka_work" \
    "$DOCKER_IMAGE" \
    bash
