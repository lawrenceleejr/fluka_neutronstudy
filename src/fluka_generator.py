"""
FLUKA input file generator for the comparison framework.

Uses the proven neutron_bpe.inp as a template, patching energy and
neutron library selection - same approach as run_fluka.sh.
"""

import os
import re
import shutil
from .config_parser import SimulationConfig, FLUKA_PARTICLES, FLUKA_NEUTRON_LIBS

# Path to the working template input file (relative to project root)
DEFAULT_TEMPLATE = "neutron_bpe.inp"


def patch_fluka_input(
    template_path: str,
    output_path: str,
    energy_gev: float,
    particle: str,
    lib_sdum: str,
    events: int,
    cycles: int,
) -> str:
    """
    Produce a runnable FLUKA input by patching the template.

    Replicates what run_fluka.sh does with sed:
    - Replace BEAM energy
    - Remove any existing LOW-PWXS card
    - Insert LOW-PWXS before RANDOMIZ
    - Set START count (events / cycles)

    Args:
        template_path: Path to the template .inp file
        output_path:   Where to write the patched file
        energy_gev:    Beam energy in GeV (negative for FLUKA momentum convention)
        particle:      FLUKA particle name (e.g. NEUTRON)
        lib_sdum:      LOW-PWXS SDUM field (≤8 chars)
        events:        Total number of primaries
        cycles:        Number of FLUKA cycles

    Returns:
        output_path
    """
    with open(template_path, 'r') as f:
        lines = f.readlines()

    # FLUKA BEAM card: negative energy = fixed kinetic energy (not momentum)
    energy_str = f"{-energy_gev:10.4E}"

    patched = []
    for line in lines:
        keyword = line[:10].strip()

        # Replace BEAM energy and particle type
        if keyword == "BEAM":
            # Fixed-format: 10 keyword + 6×10 WHAT fields + 8 SDUM
            # Keep the format the same but replace energy (WHAT1) and SDUM
            rest = line[10:]  # everything after keyword
            # Re-emit with new energy in WHAT1, same other fields, same SDUM/particle
            # Preserve original fields 2-6 by only replacing first 10-char slot
            patched.append(f"BEAM      {energy_str}       0.0       0.0       0.0       0.0       1.0{particle}\n")
            continue

        # Remove any existing LOW-PWXS card (will re-add it)
        if keyword == "LOW-PWXS":
            continue

        # Insert LOW-PWXS and updated START immediately before RANDOMIZ
        if keyword == "RANDOMIZ":
            # LOW-PWXS card: WHAT(1)=1 activates pointwise xsec, SDUM=library
            pwxs = (
                f"LOW-PWXS       1.0       0.0       0.0       0.0       0.0       0.0"
                f"{lib_sdum:<8}\n"
            )
            patched.append(pwxs)

        # Replace START count
        if keyword == "START":
            events_per_cycle = max(1, events // cycles)
            patched.append(f"START     {events_per_cycle:>9.1f}\n")
            continue

        patched.append(line)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, 'w') as f:
        f.writelines(patched)

    return output_path


def generate_fluka_input_native(
    config: SimulationConfig,
    neutron_library: str,
    output_path: str,
    template_path: str = DEFAULT_TEMPLATE,
) -> str:
    """
    Generate FLUKA input by patching the template .inp file.

    Args:
        config:          Simulation configuration
        neutron_library: Library key (JEFF, ENDF, JENDL, CENDL, BROND)
        output_path:     Destination for the patched .inp file
        template_path:   Source template (default: neutron_bpe.inp)

    Returns:
        output_path
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(
            f"Template not found: {template_path}. "
            "Pass template_path= pointing to a working FLUKA .inp file."
        )

    lib_sdum = FLUKA_NEUTRON_LIBS.get(neutron_library, neutron_library[:8])
    fluka_particle = FLUKA_PARTICLES.get(
        config.particle.type.lower(), config.particle.type.upper()
    )

    return patch_fluka_input(
        template_path=template_path,
        output_path=output_path,
        energy_gev=config.particle.energy_gev,
        particle=fluka_particle,
        lib_sdum=lib_sdum,
        events=config.events,
        cycles=config.fluka.cycles,
    )


def generate_fluka_input(
    config: SimulationConfig,
    neutron_library: str,
    output_path: str,
    template_path: str = DEFAULT_TEMPLATE,
) -> str:
    """Alias for FLUGG mode - same template patching, geometry comes from GDML."""
    return generate_fluka_input_native(
        config, neutron_library, output_path, template_path
    )
