"""
FLUKA input file generator for the comparison framework.

Generates FLUKA .inp files from simulation configuration.
Uses FLUGG mode with external GDML geometry.
"""

import os
from typing import Optional
from .config_parser import (
    SimulationConfig, FLUKA_PARTICLES, FLUKA_NEUTRON_LIBS
)


def format_fluka_card(keyword: str, what: list, sdum: str = "") -> str:
    """Format a FLUKA input card with proper fixed-width columns."""
    # FLUKA format: KEYWORD(10) WHAT1-6(10 each) SDUM(8)
    line = f"{keyword:<10}"
    for i, w in enumerate(what[:6]):
        if w is None:
            line += " " * 10
        elif isinstance(w, str):
            line += f"{w:>10}"
        else:
            line += f"{w:10.4g}"
    # Pad to reach SDUM position if needed
    while len(line) < 70:
        line += " " * 10
    line = line[:70]  # Ensure exactly 70 chars before SDUM
    line += f"{sdum:<8}"
    return line


def generate_fluka_input(
    config: SimulationConfig,
    neutron_library: str,
    output_path: str,
) -> str:
    """
    Generate FLUKA input file for FLUGG mode.

    Args:
        config: Simulation configuration
        neutron_library: Neutron library to use (JEFF, ENDF, etc.)
        output_path: Path to write the input file

    Returns:
        Path to the generated input file
    """
    particle = config.particle
    scoring = config.scoring

    # Get FLUKA particle name
    fluka_particle = FLUKA_PARTICLES.get(
        particle.type.lower(), particle.type.upper()
    )

    # Get neutron library SDUM
    lib_sdum = FLUKA_NEUTRON_LIBS.get(neutron_library, neutron_library[:8])

    # Energy in GeV (FLUKA uses GeV)
    energy_gev = particle.energy_gev

    lines = []

    # Title
    lines.append("TITLE")
    lines.append(f"FLUGG comparison run - {neutron_library} library")

    # Physics defaults
    lines.append(format_fluka_card("DEFAULTS", [None]*6, "PRECISIO"))

    # Beam definition
    # BEAM: WHAT(1)=energy, WHAT(2)=spread, WHAT(3)=divergence
    #       WHAT(4)=beam width x, WHAT(5)=beam width y
    lines.append(format_fluka_card(
        "BEAM", [-energy_gev, 0.0, 0.0, 0.0, 0.0, 1.0], fluka_particle
    ))

    # Beam position
    # BEAMPOS: WHAT(1-3)=x,y,z position, WHAT(4-5)=direction cosines
    x, y, z = particle.position
    dx, dy, dz = particle.direction
    lines.append(format_fluka_card(
        "BEAMPOS", [x, y, z, dx, dy, None], ""
    ))

    # FLUGG geometry card (tells FLUKA to use external geometry)
    lines.append(format_fluka_card("GEOBEGIN", [None]*6, "FLUGG"))
    lines.append("    0    0          FLUGG geometry from GDML")
    lines.append("GEOEND")

    # Low energy neutron transport with pointwise cross-sections
    if config.fluka.low_energy_neutron:
        lines.append(format_fluka_card(
            "LOW-PWXS", [1.0, 0.0, 0.0, 0.0, 0.0, 0.0], lib_sdum
        ))

    # Scoring: Energy deposition
    if scoring.energy_deposition.get('enabled', True):
        edep = scoring.energy_deposition
        x_range = edep.get('x_range', [-100, 100])
        y_range = edep.get('y_range', [-100, 100])
        z_range = edep.get('z_range', [0, 2])
        x_bins = edep.get('x_bins', 1)
        y_bins = edep.get('y_bins', 1)
        z_bins = edep.get('z_bins', 100)

        # USRBIN for energy deposition
        # First card: type, particle, unit, xmax, ymax, zmax
        lines.append(format_fluka_card(
            "USRBIN", [10.0, "ENERGY", -21.0, x_range[1], y_range[1], z_range[1]],
            "EDEP"
        ))
        # Second card: xmin, ymin, zmin, nx, ny, nz
        lines.append(format_fluka_card(
            "USRBIN", [x_range[0], y_range[0], z_range[0], x_bins, y_bins, z_bins],
            "&"
        ))

    # Scoring: Neutron spectrum at boundary
    if scoring.neutron_spectrum.get('enabled', True):
        spec = scoring.neutron_spectrum
        e_range = spec.get('energy_range', [1e-11, 1e1])
        e_bins = spec.get('energy_bins', 100)

        # USRBDX for boundary crossing spectrum
        # Score neutrons crossing from material to vacuum (exit)
        lines.append(format_fluka_card(
            "USRBDX", [99.0, "NEUTRON", -23.0, "YOURMAT", "VACUUM", 1.0],
            "NEUT-OUT"
        ))
        lines.append(format_fluka_card(
            "USRBDX", [e_range[1], e_range[0], e_bins, None, None, None],
            "&"
        ))

    # Random number seed
    if config.seed > 0:
        lines.append(format_fluka_card(
            "RANDOMIZ", [1.0, config.seed, None, None, None, None], ""
        ))
    else:
        lines.append(format_fluka_card(
            "RANDOMIZ", [1.0, None, None, None, None, None], ""
        ))

    # Number of primaries
    events_per_cycle = config.events // config.fluka.cycles
    lines.append(format_fluka_card(
        "START", [events_per_cycle, None, None, None, None, None], ""
    ))

    lines.append("STOP")

    # Write to file
    content = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(content)

    return output_path


def generate_fluka_input_native(
    config: SimulationConfig,
    neutron_library: str,
    output_path: str,
) -> str:
    """
    Generate FLUKA input file with native geometry (not FLUGG).

    This version includes inline geometry definition for cases
    where FLUGG is not available.

    Args:
        config: Simulation configuration
        neutron_library: Neutron library to use
        output_path: Path to write the input file

    Returns:
        Path to the generated input file
    """
    particle = config.particle
    scoring = config.scoring

    fluka_particle = FLUKA_PARTICLES.get(
        particle.type.lower(), particle.type.upper()
    )
    lib_sdum = FLUKA_NEUTRON_LIBS.get(neutron_library, neutron_library[:8])
    energy_gev = particle.energy_gev

    lines = []

    # Title
    lines.append("TITLE")
    lines.append(f"FLUKA native geometry run - {neutron_library} library")

    # Physics defaults
    lines.append(format_fluka_card("DEFAULTS", [None]*6, "PRECISIO"))

    # Beam
    lines.append(format_fluka_card(
        "BEAM", [-energy_gev, 0.0, 0.0, 0.0, 0.0, 1.0], fluka_particle
    ))

    # Beam position
    x, y, z = particle.position
    dx, dy, dz = particle.direction
    lines.append(format_fluka_card(
        "BEAMPOS", [x, y, z, dx, dy, None], ""
    ))

    # Native geometry (simple slab)
    lines.append("GEOBEGIN                                                              COMBNAME")
    lines.append("    0    0          BPE slab geometry")
    # Bodies
    lines.append("RPP world      -200. 200. -200. 200. -50. 50.")
    lines.append("RPP bpeslab    -100. 100. -100. 100. 0. 1.75")
    lines.append("END")
    # Regions
    lines.append("WORLDREG  5 +world -bpeslab")
    lines.append("BPEREGIO  5 +bpeslab")
    lines.append("END")
    lines.append("GEOEND")

    # Material assignment
    lines.append(format_fluka_card(
        "ASSIGNMA", ["VACUUM", "WORLDREG", None, None, None, None], ""
    ))
    lines.append(format_fluka_card(
        "ASSIGNMA", ["BPOLY", "BPEREGIO", None, None, None, None], ""
    ))

    # BPE material definition
    lines.append(format_fluka_card(
        "MATERIAL", [None, None, 0.95, 25, None, None], "BPOLY"
    ))
    lines.append(format_fluka_card(
        "COMPOUND", [-0.12, "HYDROGEN", -0.63, "CARBON", -0.05, "BORON"], "BPOLY"
    ))
    lines.append(format_fluka_card(
        "COMPOUND", [-0.20, "OXYGEN", None, None, None, None], "BPOLY"
    ))

    # Low energy neutrons
    if config.fluka.low_energy_neutron:
        lines.append(format_fluka_card(
            "LOW-PWXS", [1.0, 0.0, 0.0, 0.0, 0.0, 0.0], lib_sdum
        ))

    # Scoring
    if scoring.energy_deposition.get('enabled', True):
        edep = scoring.energy_deposition
        x_range = edep.get('x_range', [-100, 100])
        y_range = edep.get('y_range', [-100, 100])
        z_range = edep.get('z_range', [0, 2])
        x_bins = edep.get('x_bins', 1)
        y_bins = edep.get('y_bins', 1)
        z_bins = edep.get('z_bins', 100)

        lines.append(format_fluka_card(
            "USRBIN", [10.0, "ENERGY", -21.0, x_range[1], y_range[1], z_range[1]],
            "EDEP"
        ))
        lines.append(format_fluka_card(
            "USRBIN", [x_range[0], y_range[0], z_range[0], x_bins, y_bins, z_bins],
            "&"
        ))

    if scoring.neutron_spectrum.get('enabled', True):
        spec = scoring.neutron_spectrum
        e_range = spec.get('energy_range', [1e-11, 1e1])
        e_bins = spec.get('energy_bins', 100)

        lines.append(format_fluka_card(
            "USRBDX", [99.0, "NEUTRON", -23.0, "BPEREGIO", "WORLDREG", 1.0],
            "NEUT-OUT"
        ))
        lines.append(format_fluka_card(
            "USRBDX", [e_range[1], e_range[0], e_bins, None, None, None],
            "&"
        ))

    # Random seed
    if config.seed > 0:
        lines.append(format_fluka_card(
            "RANDOMIZ", [1.0, config.seed, None, None, None, None], ""
        ))
    else:
        lines.append(format_fluka_card(
            "RANDOMIZ", [1.0, None, None, None, None, None], ""
        ))

    # Start
    events_per_cycle = config.events // config.fluka.cycles
    lines.append(format_fluka_card(
        "START", [events_per_cycle, None, None, None, None, None], ""
    ))

    lines.append("STOP")

    # Write
    content = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(content)

    return output_path
