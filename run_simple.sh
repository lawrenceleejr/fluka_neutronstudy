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
# SETUP_SCRIPT: installs gfortran if absent (rfluka requires it to link)
# and exports FLUKA environment variables.  Run first in every mode.
# ---------------------------------------------------------------------------
SETUP_SCRIPT='
set +e
FLUPRO=/usr/local/fluka
FLUFOR=gfortran
export FLUPRO FLUFOR
export PATH="$FLUPRO/bin:$PATH"

if ! command -v gfortran &>/dev/null; then
    echo "[setup] gfortran not found — installing..."
    apt-get update -qq && apt-get install -y -qq gfortran
    echo "[setup] gfortran installed."
else
    echo "[setup] gfortran already present: $(gfortran --version | head -1)"
fi

# Install FLUKA pointwise neutron library packages if present.
# neutron_libraries/ lives in the project root, already mounted at /data.
if ls /data/neutron_libraries/fluka-pw-*.deb 2>/dev/null | head -1 >/dev/null; then
    echo "[setup] Installing FLUKA pointwise neutron library packages..."
    dpkg -i /data/neutron_libraries/fluka-pw-*.deb 2>&1 \
        || echo "[setup] WARNING: one or more packages failed to install"
    echo "[setup] Pointwise libraries installed."
else
    echo "[setup] No neutron library packages in /data/neutron_libraries/ — group-wise XS data will be used"
fi
'

# ---------------------------------------------------------------------------
# DIAG_SCRIPT: prints a full container report.  Assumes SETUP_SCRIPT ran.
# ---------------------------------------------------------------------------
DIAG_SCRIPT='
echo ""
echo "============================================================"
echo " FLUKA Container Diagnostics"
echo "============================================================"

echo ""
echo "--- FLUKA installation path ($FLUPRO) ---"
if [ -d "$FLUPRO" ]; then
    ls "$FLUPRO"
else
    echo "WARNING: $FLUPRO does not exist!"
fi

echo ""
echo "--- Compiler (required by rfluka) ---"
if command -v gfortran &>/dev/null; then
    echo "  [OK]  gfortran: $(gfortran --version | head -1)"
else
    echo "  [!!]  gfortran: NOT FOUND — rfluka cannot link without it"
fi

echo ""
echo "--- Key FLUKA utilities ---"
for util in rfluka usbsuw usbrea usxsuw usxrea; do
    p="$FLUPRO/bin/$util"
    if [ -x "$p" ]; then
        echo "  [OK]  $p"
    else
        echo "  [!!]  $p  <-- NOT FOUND"
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
    echo "  (pointwise libraries like JEFF-3.3 are not in the stock image)"
fi

echo ""
echo "--- Wider filesystem search for JEFF/ENDF/JENDL files ---"
wide=$(find / -maxdepth 6 \( -name "JEFF*" -o -name "ENDFB*" -o -name "JENDL*" -o -name "*.nds" \) 2>/dev/null | head -20)
if [ -n "$wide" ]; then
    echo "$wide" | sed "s/^/  /"
else
    echo "  None found"
fi

echo ""
echo "--- rfluka self-report ---"
"$FLUPRO/bin/rfluka" -h 2>&1 | head -8 || echo "  rfluka -h failed"

echo ""
echo "============================================================"
'

# ---------------------------------------------------------------------------
# CHEATSHEET: printed when the interactive shell starts
# ---------------------------------------------------------------------------
CHEATSHEET='
echo ""
echo "============================================================"
echo " FLUKA Debug Cheatsheet  (env already set, input file staged)"
echo "============================================================"
echo "  \$FLUPRO/bin/rfluka -N0 -M1 neutron_bpe   # run 1 cycle"
echo "  \$FLUPRO/bin/rfluka -N0 -M1 neutron_bpe 2>&1 | tee run.log"
echo "  tail -f neutron_bpe001.out                # watch live"
echo "  cat neutron_bpe001.err                    # check errors"
echo "  ls \$FLUPRO/data/                          # group XS data"
echo "  find \$FLUPRO -name \"*.nds\"                # pointwise XS libs"
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
            bash -c "$SETUP_SCRIPT
$DIAG_SCRIPT"
        ;;

    --check)
        echo "Running single-cycle FLUKA check..."
        mkdir -p output/debug_check

        docker run --rm \
            -v "$(pwd):/data" \
            -w "/fluka_work" \
            "$DOCKER_IMAGE" \
            bash -c "$SETUP_SCRIPT
$DIAG_SCRIPT

echo ''
echo '============================================================'
echo ' Test run: rfluka -N0 -M1'
echo '============================================================'

mkdir -p /fluka_work
cd /fluka_work
cp /data/$INPUT_FILE .

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
echo '--- Output files ---'
mkdir -p /data/output/debug_check
cp -f *.out /data/output/debug_check/ 2>/dev/null || true
cp -f *.err /data/output/debug_check/ 2>/dev/null || true
cp -f *.log /data/output/debug_check/ 2>/dev/null || true
cp -f *_fort.* /data/output/debug_check/ 2>/dev/null || true
ls -lh /data/output/debug_check/

exit \$FLUKA_RC"
        echo ""
        echo "Logs saved to: output/debug_check/"
        ;;

    ""|--interactive)
        echo "Starting interactive FLUKA debug shell..."
        echo "(Run './run_simple.sh --diagnose' for a non-interactive report)"
        echo ""

        BASHRC="$SETUP_SCRIPT
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
        # Write rcfile to a host temp file and mount it — process substitution
        # (<(...)) creates a host-side fd that doesn't exist inside Docker.
        TMPRC=$(mktemp /tmp/fluka_rc_XXXXXX.sh)
        echo "$BASHRC" > "$TMPRC"
        docker run -it --rm \
            -v "$(pwd):/data" \
            -v "$TMPRC:/tmp/fluka_rc.sh:ro" \
            -w "/fluka_work" \
            "$DOCKER_IMAGE" \
            bash --rcfile /tmp/fluka_rc.sh
        rm -f "$TMPRC"
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
