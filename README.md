# FLUKA Neutron Capture Study

Monte Carlo simulation of neutron capture in borated polyethylene using FLUKA.

## Overview

This project simulates a 1 MeV neutron traveling through a block of borated polyethylene (BPE), commonly used for neutron shielding. The simulation tracks energy deposition as neutrons are moderated and captured.

### Physics

- **Material**: Borated polyethylene (5% B by weight, density 0.95 g/cm³)
- **Source**: 1 MeV neutron at origin, directed along +Z axis
- **Geometry**: 20×20×40 cm³ BPE block

Boron-10 has a high thermal neutron capture cross-section (~3840 barns), making BPE effective for neutron shielding. The hydrogen in polyethylene moderates fast neutrons, and boron captures the thermalized neutrons.

## Prerequisites

- Docker with the `fluka:ggi` image
- Python 3 with numpy and matplotlib

## Files

| File | Description |
|------|-------------|
| `neutron_bpe.inp` | FLUKA input file defining geometry, materials, and scoring |
| `run_fluka.sh` | Script to run FLUKA simulation in Docker container |
| `run_simple.sh` | Interactive Docker script for debugging |
| `plot_edep.py` | Matplotlib visualization of energy deposition |

## Usage

### 1. Run the Simulation

```bash
chmod +x run_fluka.sh
./run_fluka.sh 5  # Run 5 cycles (default)
```

This will:
- Start the FLUKA container
- Run the simulation with the specified number of cycles
- Process binary output to ASCII format
- Copy results to `./output/`

### 2. Visualize Results

```bash
python3 plot_edep.py
```

Or specify a different output directory:

```bash
python3 plot_edep.py ./output
```

The script will:
- Read USRBIN output files (ASCII or binary)
- Create an XZ projection plot of energy deposition
- Save to `edep_xz_plot.png`

If no simulation output exists, it creates a demonstration plot.

### Interactive Mode

For debugging or manual runs:

```bash
./run_simple.sh
```

Then inside the container:

```bash
cd /fluka_work
cp /data/neutron_bpe.inp .
$FLUPRO/flutil/rfluka -N0 -M1 neutron_bpe
```

## FLUKA Input Details

### Geometry (GEOBEGIN/GEOEND)

```
BPE block:   -10 to 10 cm (X), -10 to 10 cm (Y), -5 to 35 cm (Z)
Air region:  -50 to 50 cm in all directions
Black hole:  -100 to 100 cm (particle absorber boundary)
```

### Scoring (USRBIN)

Two USRBIN detectors configured:

1. **EDEP-XZ** (unit 21): 2D XZ projection
   - 100 bins in X, 1 bin in Y, 200 bins in Z
   - Integrated over Y direction

2. **EDEP-3D** (unit 22): Full 3D energy deposition
   - 50×50×100 bins

### Materials

- **BPOLY**: Borated polyethylene compound
  - 11.9% H, 63.1% C, 5% B by mass
  - Density: 0.95 g/cm³

## Output Files

After simulation:

| File | Description |
|------|-------------|
| `*.out` | FLUKA output log |
| `*_fort.21` | USRBIN binary (XZ projection) |
| `*_fort.22` | USRBIN binary (3D) |
| `edep_xz.bnn` | Merged USRBIN binary |
| `edep_xz.dat` | ASCII format for plotting |

## Adjusting Parameters

### Number of primaries

Edit `neutron_bpe.inp`, change the START card:

```
START        10000.0    <- Number of primary neutrons
```

### Neutron energy

Edit the BEAM card (energy in GeV):

```
BEAM           0.001    <- 1 MeV = 0.001 GeV
```

### Block dimensions

Edit the RPP body `bpeblk` in the geometry section.

## License

For research and educational purposes.
