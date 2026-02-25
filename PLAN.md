# FLUKA vs Geant4 Comparison Tool - Implementation Plan

## Overview

Create a unified simulation framework that allows apples-to-apples comparisons between FLUKA (via FLUGG) and Geant4, given:
- A generic GDML geometry
- A particle gun definition
- Configurable physics options for each code
- Batch mode: scan over multiple physics lists and neutron models
- Separate analysis stage for multi-model comparison plots

## Configuration Files

### 1. Simulation Config (`config/simulation_config.yaml`)

```yaml
# Particle gun definition
particle:
  type: electron          # electron, positron, photon, muon, neutron, proton
  energy: 1500.0          # GeV
  position: [0, 0, -100]  # Starting point [x, y, z] in cm
  direction: [0, 0, 1]    # Direction unit vector [dx, dy, dz]

# Geometry
geometry:
  gdml: gdml/bpe_slab.gdml    # Path to GDML file

# Simulation parameters
simulation:
  events: 10000           # Number of primary particles
  output_dir: output/scan_results  # Base output directory

# FLUKA/FLUGG settings
fluka:
  enabled: true
  cycles: 5               # FLUKA cycles (events split across cycles)
  # List of neutron libraries to scan
  neutron_libraries:
    - JEFF
    - ENDF
    - JENDL
    - CENDL
    - BROND
  low_energy_neutron: true  # Enable pointwise neutron transport

# Geant4 settings
geant4:
  enabled: true
  cut_value: 1.0          # Production cut in mm
  # List of physics lists to scan
  physics_lists:
    - FTFP_BERT
    - FTFP_BERT_HP
    - QGSP_BERT
    - QGSP_BERT_HP
    - QGSP_BIC_HP
    - Shielding

# Scoring configuration
scoring:
  # Energy deposition binning
  energy_deposition:
    enabled: true
    x_bins: 50
    y_bins: 1
    z_bins: 100
    x_range: [-100, 100]   # cm
    y_range: [-100, 100]   # cm
    z_range: [0, 1.75]     # cm (match slab)

  # Neutron spectrum at exit
  neutron_spectrum:
    enabled: true
    energy_bins: 100
    energy_range: [1e-9, 1e4]  # GeV (log scale)

  # Secondary particle tracking
  secondaries:
    enabled: true
    particles: [neutron, photon, electron, proton]
```

### 2. Analysis Config (`config/analysis_config.yaml`)

```yaml
# Analysis configuration for comparing multiple simulation results

# Directory containing simulation results
results_dir: output/scan_results

# Which results to include (auto-detect if empty)
include:
  fluka:
    - JEFF
    - ENDF
    - JENDL
  geant4:
    - FTFP_BERT_HP
    - QGSP_BIC_HP
    - Shielding

# Reference model for ratio plots
reference:
  code: fluka
  model: JEFF

# Plot settings
plots:
  # 1D energy deposition profile (z-projection)
  edep_profile_z:
    enabled: true
    log_scale: true
    show_ratio: true
    output: edep_profile_z.png

  # 2D energy deposition map
  edep_map_xz:
    enabled: true
    log_scale: true
    output: edep_map_xz.png

  # Neutron exit spectrum
  neutron_spectrum:
    enabled: true
    log_scale: true
    show_ratio: true
    output: neutron_spectrum.png

  # Total energy deposited comparison
  total_edep_bar:
    enabled: true
    output: total_edep_comparison.png

  # Model spread / uncertainty band
  model_spread:
    enabled: true
    output: model_spread.png

# Output
output_dir: output/analysis
formats: [png, pdf]  # Output formats
dpi: 150
```

## File Structure

```
fluka_neutronstudy/
├── run_comparison.py          # Main orchestration script (batch mode)
├── analyze_results.py         # Analysis/plotting script
├── config/
│   ├── simulation_config.yaml # Simulation settings
│   ├── analysis_config.yaml   # Analysis settings
│   └── material_mapping.json  # G4→FLUKA material map (existing)
├── src/
│   ├── config_parser.py       # YAML config parsing & validation
│   ├── fluka_generator.py     # Generate FLUKA input from config
│   ├── geant4_generator.py    # Generate G4 macro from config
│   ├── runner.py              # Docker execution helpers
│   └── analysis/
│       ├── reader.py          # Read FLUKA and G4 outputs
│       ├── normalize.py       # Normalization utilities
│       └── plotter.py         # Comparison plotting
├── docker/
│   ├── Dockerfile.flugg       # FLUGG container (existing)
│   ├── geant4_app/
│   │   ├── CMakeLists.txt     # Build system for G4 app
│   │   ├── src/
│   │   │   ├── main.cc        # Main Geant4 application
│   │   │   ├── DetectorConstruction.cc  # GDML loader
│   │   │   ├── PrimaryGeneratorAction.cc
│   │   │   ├── RunAction.cc
│   │   │   ├── EventAction.cc
│   │   │   └── SteppingAction.cc  # Scoring
│   │   └── include/           # Headers
│   └── run_geant4.sh          # G4 runner script
├── gdml/
│   └── bpe_slab.gdml          # BPE slab geometry (existing)
└── output/                    # Results (gitignored)
```

## Docker Images

| Purpose | Image |
|---------|-------|
| FLUGG (FLUKA + G4 geometry) | `flugg:latest` (built from fluka:ggi) |
| Geant4 | `ghcr.io/kalradaisy/geant4muc:dev-CI` |

## Output Structure

```
output/scan_results/
├── metadata.yaml              # Scan metadata (timestamp, config hash)
├── fluka/
│   ├── JEFF/
│   │   ├── input.inp
│   │   ├── edep.dat
│   │   ├── neutron_spectrum.dat
│   │   └── run.log
│   ├── ENDF/
│   │   └── ...
│   ├── JENDL/
│   ├── CENDL/
│   └── BROND/
├── geant4/
│   ├── FTFP_BERT/
│   │   ├── run.mac
│   │   ├── edep.csv
│   │   ├── neutron_spectrum.csv
│   │   └── run.log
│   ├── FTFP_BERT_HP/
│   ├── QGSP_BERT/
│   ├── QGSP_BERT_HP/
│   ├── QGSP_BIC_HP/
│   └── Shielding/
└── summary.csv                # Quick summary of all runs

output/analysis/
├── edep_profile_z.png         # All models on one plot
├── edep_profile_z.pdf
├── neutron_spectrum.png
├── total_edep_comparison.png
├── model_spread.png
├── ratio_to_JEFF.png
└── summary_table.csv          # Numerical comparison
```

## Implementation Steps

### Phase 1: Core Framework

1. **Config parser** (`src/config_parser.py`)
   - Parse and validate YAML configs
   - Expand model lists into individual run configs
   - Generate unique run IDs

2. **FLUKA generator** (`src/fluka_generator.py`)
   - Generate FLUKA .inp from config + neutron library
   - Handle beam, scoring, physics settings

3. **Geant4 generator** (`src/geant4_generator.py`)
   - Generate run.mac from config + physics list
   - Match scoring binning to FLUKA

4. **Runner** (`src/runner.py`)
   - Execute Docker containers
   - Handle parallelization
   - Track progress and failures

### Phase 2: Geant4 Application

5. **Geant4 application** (`docker/geant4_app/`)
   - GDML geometry loader
   - Command-line physics list selection
   - Scoring matching FLUKA output format
   - CSV output for easy parsing

6. **Build in Docker**
   - Compile G4 app in geant4muc container
   - Create runner script

### Phase 3: Batch Execution

7. **Batch runner** (`run_comparison.py`)
   - Parse config, expand model lists
   - Run all FLUKA variants
   - Run all Geant4 variants
   - Collect results, generate summary

### Phase 4: Analysis

8. **Result reader** (`src/analysis/reader.py`)
   - Read FLUKA ASCII output
   - Read Geant4 CSV output
   - Normalize to common units

9. **Plotter** (`src/analysis/plotter.py`)
   - Multi-model overlay plots
   - Ratio plots vs reference
   - Model spread / uncertainty bands
   - Summary bar charts

10. **Analysis script** (`analyze_results.py`)
    - Parse analysis config
    - Load specified results
    - Generate all configured plots

## Usage

```bash
# Run full scan (all FLUKA neutron libs + all G4 physics lists)
python3 run_comparison.py config/simulation_config.yaml

# Run only FLUKA models
python3 run_comparison.py config/simulation_config.yaml --fluka-only

# Run only Geant4 models
python3 run_comparison.py config/simulation_config.yaml --geant4-only

# Run specific models only
python3 run_comparison.py config/simulation_config.yaml \
    --fluka-models JEFF,ENDF \
    --geant4-models FTFP_BERT_HP,Shielding

# Analyze results (separate step)
python3 analyze_results.py config/analysis_config.yaml

# Quick analysis with defaults
python3 analyze_results.py --results-dir output/scan_results
```

## Physics Models Reference

### FLUKA Neutron Libraries

| Library | Source | Best for |
|---------|--------|----------|
| JEFF-3.3 | Europe (NEA) | General purpose, well validated |
| ENDF/B-VIII.0 | USA (BNL) | US standard, extensive validation |
| JENDL-4.0u | Japan (JAEA) | Asian materials, actinides |
| CENDL-3.1 | China (CIAE) | Chinese evaluations |
| BROND-3.1 | Russia (IPPE) | Russian evaluations |

### Geant4 Physics Lists

| Physics List | Neutron Model | Best for |
|--------------|---------------|----------|
| FTFP_BERT | Bertini <10GeV | General HEP |
| FTFP_BERT_HP | + HP neutrons <20MeV | Neutron transport |
| QGSP_BERT | Bertini <10GeV | Alternative to FTFP |
| QGSP_BERT_HP | + HP neutrons | Neutron + shielding |
| QGSP_BIC_HP | Binary cascade + HP | Low-E nuclear |
| Shielding | Optimized for shielding | Dosimetry, shielding |

## Key Considerations

1. **Normalization**: All outputs in GeV/cm³/primary
2. **Binning**: Identical scoring bins for direct comparison
3. **Statistics**: Same number of primaries (track in metadata)
4. **Materials**: Verify G4 materials match FLUKA definitions
5. **Geometry**: Same GDML ensures identical geometry
6. **Reproducibility**: Store configs, seeds, versions in metadata

## Example Comparison Plot

```
┌─────────────────────────────────────────────────────────────┐
│  Energy Deposition Profile (Z)                              │
│                                                             │
│  ━━━ FLUKA/JEFF        ━━━ G4/FTFP_BERT_HP                 │
│  ─── FLUKA/ENDF        ─── G4/QGSP_BIC_HP                  │
│  ··· FLUKA/JENDL       ··· G4/Shielding                    │
│                                                             │
│  10⁻⁴ ┤                                                    │
│       │    ╭──╮                                            │
│  10⁻⁵ ┤   ╱    ╲                                           │
│       │  ╱      ╲                                          │
│  10⁻⁶ ┤─╱────────╲─────────────────────────────            │
│       │                                                     │
│  10⁻⁷ ┤                                                    │
│       └────────────────────────────────────────────        │
│         0.0      0.5      1.0      1.5      2.0            │
│                       Z (cm)                                │
├─────────────────────────────────────────────────────────────┤
│  Ratio to FLUKA/JEFF                                        │
│  1.2 ┤                                                     │
│  1.0 ┤━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━             │
│  0.8 ┤                                                     │
│      └────────────────────────────────────────────         │
└─────────────────────────────────────────────────────────────┘
```

