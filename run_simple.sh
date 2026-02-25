#!/bin/bash
# Interactive debugging launcher for the FLUKA container.
#
# Usage:
#   ./run_simple.sh              # interactive bash shell (default)
#   ./run_simple.sh --diagnose   # print container diagnostics and exit
#   ./run_simple.sh --check      # run a single-cycle test and dump logs

DOCKER_IMAGE="fluka:ggi"
INPUT_FILE="neutron_bpe.inp"

# ---------------------------------------------------------------------------
# Inline script that runs inside the container to set up the environment
# and print diagnostics. Used by all three modes.
# ---------------------------------------------------------------------------
DIAG_SCRIPT='
set +e
FLUPRO=/usr/local/fluka
FLUFOR=gfortran
export FLUPRO FLUFOR
export PATH="$FLUPRO/bin:$PATH"

echo ""
echo "============================================================"
echo " FLUKA Container Diagnostics"
echo "============================================================"

echo ""
echo "--- FLUKA installation path ---"
if [ -d "$FLUPRO" ]; then
    ls "$FLUPRO"
else
    echo "WARNING: $FLUPRO does not exist!"
fi

echo ""
echo "--- Key utilities ---"
for util in rfluka usbsuw usbrea usxsuw usxrea; do
    path="$FLUPRO/bin/$util"
    if [ -x "$path" ]; then
        echo "  [OK]  $path"
    else
        echo "  [!!]  $path  <-- NOT FOUND"
    fi
done

echo ""
echo "--- Low-energy neutron group cross-section data (built-in) ---"
for d in "$FLUPRO/data" "$FLUPRO/neutrondata"; do
    if [ -d "$d" ]; then
        echo "  $d:"
        ls "$d" | sed "s/^/    /"
    else
        echo "  $d: not present"
    fi
done

echo ""
echo "--- Pointwise neutron XS libraries (LOW-PWXS, optional) ---"
found=$(find "$FLUPRO" -name "*.nds" 2>/dev/null)
if [ -n "$found" ]; then
    echo "$found" | sed "s/^/  /"
else
    echo "  None found under $FLUPRO"
fi

echo ""
echo "--- Searching wider filesystem for JEFF/ENDF/JENDL library files ---"
wide=$(find / -maxdepth 6 \( -name "JEFF*" -o -name "ENDFB*" -o -name "JENDL*" -o -name "*.nds" \) 2>/dev/null | head -20)
if [ -n "$wide" ]; then
    echo "$wide" | sed "s/^/  /"
else
    echo "  None found (pointwise XS libraries likely not installed)"
fi

echo ""
echo "--- rfluka self-test (version/help) ---"
"$FLUPRO/bin/rfluka" -h 2>&1 | head -8 || echo "  rfluka -h failed"

echo ""
echo "============================================================"
'

# ---------------------------------------------------------------------------
# Cheatsheet banner printed at the start of the interactive shell
# ---------------------------------------------------------------------------
CHEATSHEET='
echo ""
echo "============================================================"
echo " FLUKA Debug Cheatsheet"
echo "============================================================"
echo "  cd /fluka_work                         # working directory"
echo "  cp /data/neutron_bpe.inp .             # (already done)"
echo '\''\$FLUPRO/bin/rfluka -N0 -M1 neutron_bpe  # run 1 cycle'\''
echo '\''\$FLUPRO/bin/rfluka -N0 -M1 neutron_bpe 2>&1 | tee run.log'\''
echo "  tail -f neutron_bpe001.out             # watch output live"
echo "  cat neutron_bpe001.err                 # check errors"
echo "  ls \$FLUPRO/data/                       # group XS data"
echo "  find \$FLUPRO -name \"*.nds\"             # pointwise XS libs"
echo "============================================================"
echo ""
'

# ---------------------------------------------------------------------------
# Mode dispatch
# ---------------------------------------------------------------------------
case "${1:-}" in

    --diagnose)
        echo "Running FLUKA container diagnostics..."
        docker run --rm \
            -v "$(pwd):/data" \
            "$DOCKER_IMAGE" \
            bash -c "$DIAG_SCRIPT"
        ;;

    --check)
        echo "Running single-cycle FLUKA check..."
        mkdir -p output/debug_check

        docker run --rm \
            -v "$(pwd):/data" \
            -w "/fluka_work" \
            "$DOCKER_IMAGE" \
            bash -c "
$DIAG_SCRIPT

echo ''
echo '============================================================'
echo ' Test run: rfluka -N0 -M1'
echo '============================================================'

FLUPRO=/usr/local/fluka
FLUFOR=gfortran
export FLUPRO FLUFOR
export PATH=\"\$FLUPRO/bin:\$PATH\"

mkdir -p /fluka_work
cd /fluka_work
cp /data/$INPUT_FILE .

# Strip pointwise library cards (not available in stock image)
sed -i '/^LOW-PWXS/d' $INPUT_FILE

echo 'Input file prepared. Starting rfluka...'
echo ''

\$FLUPRO/bin/rfluka -N0 -M1 neutron_bpe
FLUKA_RC=\$?

echo ''
echo '--- neutron_bpe001.out (last 60 lines) ---'
tail -60 neutron_bpe001.out 2>/dev/null || echo '(no .out file)'
echo ''
echo '--- neutron_bpe001.err ---'
cat neutron_bpe001.err 2>/dev/null || echo '(no .err file)'
echo ''
echo '--- neutron_bpe001.log ---'
cat neutron_bpe001.log 2>/dev/null || echo '(no .log file)'

echo ''
echo '--- Copying logs to /data/output/debug_check/ ---'
mkdir -p /data/output/debug_check
cp -f *.out /data/output/debug_check/ 2>/dev/null || true
cp -f *.err /data/output/debug_check/ 2>/dev/null || true
cp -f *.log /data/output/debug_check/ 2>/dev/null || true
cp -f *_fort.* /data/output/debug_check/ 2>/dev/null || true
ls -lh /data/output/debug_check/

exit \$FLUKA_RC
"
        echo ""
        echo "Logs saved to: output/debug_check/"
        ;;

    ""|--interactive)
        echo "Starting interactive FLUKA debug shell..."
        echo "(Run './run_simple.sh --diagnose' for a non-interactive report)"
        echo ""

        # Build the .bashrc that runs inside the container
        BASHRC="
$DIAG_SCRIPT
$CHEATSHEET

# Stage the input file so it is ready to use
mkdir -p /fluka_work
cd /fluka_work
if [ -f /data/$INPUT_FILE ]; then
    cp /data/$INPUT_FILE .
    echo 'Input file staged: /fluka_work/$INPUT_FILE'
    echo ''
fi

export PS1='[fluka-debug \w]\$ '
"
        docker run -it --rm \
            -v "$(pwd):/data" \
            -w "/fluka_work" \
            "$DOCKER_IMAGE" \
            bash --rcfile <(echo "$BASHRC")
        ;;

    *)
        echo "Usage: $0 [--diagnose | --check]"
        echo ""
        echo "  (no args)    Interactive bash shell with FLUKA environment"
        echo "  --diagnose   Print container diagnostics and exit"
        echo "  --check      Run a single-cycle FLUKA test and dump logs"
        exit 1
        ;;
esac
