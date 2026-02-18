"""
Geant4 macro file generator for the comparison framework.

Generates Geant4 macro files from simulation configuration.
"""

import os
from typing import Optional
from .config_parser import SimulationConfig, GEANT4_PARTICLES


def generate_geant4_macro(
    config: SimulationConfig,
    physics_list: str,
    output_path: str,
) -> str:
    """
    Generate Geant4 macro file.

    Args:
        config: Simulation configuration
        physics_list: Geant4 physics list to use
        output_path: Path to write the macro file

    Returns:
        Path to the generated macro file
    """
    particle = config.particle
    scoring = config.scoring

    # Get Geant4 particle name
    g4_particle = GEANT4_PARTICLES.get(
        particle.type.lower(), particle.type.lower()
    )

    # Energy in MeV (Geant4 default units)
    energy_mev = particle.energy_mev

    lines = []

    # Header comment
    lines.append(f"# Geant4 macro for comparison framework")
    lines.append(f"# Physics list: {physics_list}")
    lines.append("")

    # Verbosity
    lines.append("# Verbosity settings")
    lines.append("/control/verbose 0")
    lines.append("/run/verbose 0")
    lines.append("/event/verbose 0")
    lines.append("/tracking/verbose 0")
    lines.append("")

    # Initialize (physics list set via command line)
    lines.append("# Initialize run")
    lines.append("/run/initialize")
    lines.append("")

    # Production cuts
    lines.append("# Production cuts")
    lines.append(f"/run/setCut {config.geant4.cut_value} mm")
    lines.append("")

    # Particle gun setup
    lines.append("# Particle gun configuration")
    lines.append(f"/gun/particle {g4_particle}")
    lines.append(f"/gun/energy {energy_mev} MeV")

    x, y, z = particle.position
    lines.append(f"/gun/position {x} {y} {z} cm")

    dx, dy, dz = particle.direction
    lines.append(f"/gun/direction {dx} {dy} {dz}")
    lines.append("")

    # Scoring setup (via custom commands in the application)
    if scoring.energy_deposition.get('enabled', True):
        edep = scoring.energy_deposition
        lines.append("# Energy deposition scoring")
        lines.append(f"/scoring/edep/xBins {edep.get('x_bins', 1)}")
        lines.append(f"/scoring/edep/yBins {edep.get('y_bins', 1)}")
        lines.append(f"/scoring/edep/zBins {edep.get('z_bins', 100)}")
        x_range = edep.get('x_range', [-100, 100])
        y_range = edep.get('y_range', [-100, 100])
        z_range = edep.get('z_range', [0, 2])
        lines.append(f"/scoring/edep/xRange {x_range[0]} {x_range[1]} cm")
        lines.append(f"/scoring/edep/yRange {y_range[0]} {y_range[1]} cm")
        lines.append(f"/scoring/edep/zRange {z_range[0]} {z_range[1]} cm")
        lines.append("")

    if scoring.neutron_spectrum.get('enabled', True):
        spec = scoring.neutron_spectrum
        lines.append("# Neutron spectrum scoring")
        lines.append(f"/scoring/spectrum/nBins {spec.get('energy_bins', 100)}")
        e_range = spec.get('energy_range', [1e-11, 1e1])
        # Convert to MeV for Geant4
        lines.append(f"/scoring/spectrum/eMin {e_range[0] * 1000} MeV")
        lines.append(f"/scoring/spectrum/eMax {e_range[1] * 1000} MeV")
        lines.append("")

    # Random seed
    if config.seed > 0:
        lines.append("# Random seed")
        lines.append(f"/random/setSeeds {config.seed} {config.seed + 1}")
        lines.append("")

    # Run
    lines.append("# Run simulation")
    lines.append(f"/run/beamOn {config.events}")
    lines.append("")

    # Write to file
    content = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(content)

    return output_path


def generate_geant4_config_json(
    config: SimulationConfig,
    physics_list: str,
    output_path: str,
) -> str:
    """
    Generate JSON configuration for Geant4 application.

    This provides an alternative to macro-based configuration,
    allowing all settings to be passed as a single JSON file.

    Args:
        config: Simulation configuration
        physics_list: Geant4 physics list to use
        output_path: Path to write the JSON file

    Returns:
        Path to the generated JSON file
    """
    import json

    particle = config.particle
    scoring = config.scoring

    g4_particle = GEANT4_PARTICLES.get(
        particle.type.lower(), particle.type.lower()
    )

    cfg = {
        "physics_list": physics_list,
        "geometry_gdml": config.geometry_gdml,
        "particle": {
            "type": g4_particle,
            "energy_mev": particle.energy_mev,
            "position_cm": list(particle.position),
            "direction": list(particle.direction),
        },
        "events": config.events,
        "cut_mm": config.geant4.cut_value,
        "seed": config.seed,
        "scoring": {
            "energy_deposition": scoring.energy_deposition,
            "neutron_spectrum": scoring.neutron_spectrum,
        },
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(cfg, f, indent=2)

    return output_path
