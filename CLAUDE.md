# CLAUDE.md - AI Assistant Guide

This document provides context for AI assistants working with this FLUKA neutron capture simulation project.

## Project Overview

Monte Carlo simulation of 1 MeV neutron transport and capture in borated polyethylene using the FLUKA radiation transport code. The project runs FLUKA inside a Docker container (`fluka:ggi`) and visualizes results with Python/matplotlib.

## Codebase Structure

```
fluka_neutronstudy/
├── neutron_bpe.inp     # FLUKA input file (fixed-format)
├── run_fluka.sh        # Docker execution script
├── run_simple.sh       # Interactive debugging script
├── plot_edep.py        # Matplotlib visualization
├── output/             # Simulation results (generated)
├── README.md           # User documentation
└── CLAUDE.md           # This file
```

## Key Technical Details

### FLUKA Input Format

FLUKA uses fixed-width columns (typically 10 characters per field). The format is:

```
KEYWORD    WHAT(1)   WHAT(2)   WHAT(3)   WHAT(4)   WHAT(5)   WHAT(6)   SDUM
```

Key cards in this project:
- `DEFAULTS PRECISIO` - Physics preset for precision
- `GEOBEGIN/GEOEND` - Combinatorial geometry
- `MATERIAL/COMPOUND` - Material definitions
- `BEAM/BEAMPOS` - Particle source
- `USRBIN` - Mesh-based scoring
- `LOW-NEUT` - Low energy neutron transport

### Docker Workflow

The simulation runs in the `fluka:ggi` container:
1. Mount local directory to `/data`
2. Copy input to `/fluka_work`
3. Run with `$FLUPRO/flutil/rfluka`
4. Process output with `usbsuw` (merge) and `usbrea` (ASCII conversion)
5. Copy results back to host

### Output Files

FLUKA USRBIN produces binary files (`*_fort.XX`). These are:
- Merged with `usbsuw` → `.bnn` files
- Converted to ASCII with `usbrea` → `.dat` files

The plotting script handles both formats.

## Development Guidelines

### Modifying the FLUKA Input

1. **Geometry changes**: Edit RPP bodies in GEOBEGIN section
2. **Scoring changes**: Modify USRBIN cards (unit numbers 21, 22)
3. **Physics**: Adjust DEFAULTS card or add specific physics cards
4. **Statistics**: Increase START value for more primaries

### Modifying the Plotting Script

The `plot_edep.py` script:
- Reads USRBIN ASCII/binary output
- Creates 2D XZ projection
- Falls back to sample data if no output exists

Key functions:
- `read_usrbin_ascii()` - Parse usbrea output
- `read_fort_file()` - Read binary directly
- `plot_energy_deposition()` - Create matplotlib figure

### Running Tests

No automated tests exist. Verify changes by:
1. Running simulation: `./run_fluka.sh 1`
2. Checking output files exist in `./output/`
3. Running visualization: `python3 plot_edep.py`

## Common Tasks

### Add a new scoring region

1. Add USRBIN card pair in `neutron_bpe.inp` with new unit number
2. Update `run_fluka.sh` to process the new unit
3. Update `plot_edep.py` to read/display new data

### Change material composition

Edit the COMPOUND card in `neutron_bpe.inp`:

```
COMPOUND       -0.119  HYDROGEN    -0.631    CARBON   -0.05     BORONBPOLY
```

Negative values = mass fractions. Must sum to ~1.0.

### Modify beam parameters

- Energy: BEAM card WHAT(1) in GeV
- Position: BEAMPOS card WHAT(1-3) for x,y,z
- Direction: BEAMPOS card WHAT(4-5) for direction cosines

## Dependencies

- Docker with `fluka:ggi` image
- Python 3.6+
- numpy
- matplotlib

## Debugging Tips

1. **FLUKA errors**: Check `*.out` files in output directory
2. **No output**: Use `run_simple.sh` for interactive debugging
3. **Plot issues**: Script creates sample data if no FLUKA output found
4. **Binary format**: FLUKA uses Fortran unformatted I/O with record markers
