"""
Configuration parser for FLUKA vs Geant4 comparison framework.

Handles parsing and validation of simulation and analysis YAML configs.
"""

import yaml
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path


@dataclass
class ParticleConfig:
    """Particle gun configuration."""
    type: str
    energy: float
    energy_unit: str
    position: Tuple[float, float, float]
    direction: Tuple[float, float, float]

    @property
    def energy_gev(self) -> float:
        """Return energy in GeV."""
        if self.energy_unit.upper() == 'GEV':
            return self.energy
        elif self.energy_unit.upper() == 'MEV':
            return self.energy / 1000.0
        elif self.energy_unit.upper() == 'KEV':
            return self.energy / 1e6
        elif self.energy_unit.upper() == 'EV':
            return self.energy / 1e9
        else:
            raise ValueError(f"Unknown energy unit: {self.energy_unit}")

    @property
    def energy_mev(self) -> float:
        """Return energy in MeV."""
        return self.energy_gev * 1000.0


@dataclass
class ScoringConfig:
    """Scoring configuration."""
    energy_deposition: Dict
    neutron_spectrum: Dict
    secondaries: Dict


@dataclass
class FlukaConfig:
    """FLUKA-specific configuration."""
    enabled: bool
    cycles: int
    neutron_libraries: List[str]
    low_energy_neutron: bool


@dataclass
class Geant4Config:
    """Geant4-specific configuration."""
    enabled: bool
    cut_value: float
    physics_lists: List[str]


@dataclass
class SimulationConfig:
    """Complete simulation configuration."""
    particle: ParticleConfig
    geometry_gdml: str
    events: int
    output_dir: str
    seed: int
    fluka: FlukaConfig
    geant4: Geant4Config
    scoring: ScoringConfig

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'SimulationConfig':
        """Load configuration from YAML file."""
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)

        particle = ParticleConfig(
            type=data['particle']['type'],
            energy=data['particle']['energy'],
            energy_unit=data['particle'].get('energy_unit', 'MeV'),
            position=tuple(data['particle']['position']),
            direction=tuple(data['particle']['direction']),
        )

        fluka = FlukaConfig(
            enabled=data['fluka']['enabled'],
            cycles=data['fluka']['cycles'],
            neutron_libraries=data['fluka']['neutron_libraries'],
            low_energy_neutron=data['fluka'].get('low_energy_neutron', True),
        )

        geant4 = Geant4Config(
            enabled=data['geant4']['enabled'],
            cut_value=data['geant4']['cut_value'],
            physics_lists=data['geant4']['physics_lists'],
        )

        scoring = ScoringConfig(
            energy_deposition=data['scoring']['energy_deposition'],
            neutron_spectrum=data['scoring']['neutron_spectrum'],
            secondaries=data['scoring']['secondaries'],
        )

        return cls(
            particle=particle,
            geometry_gdml=data['geometry']['gdml'],
            events=data['simulation']['events'],
            output_dir=data['simulation']['output_dir'],
            seed=data['simulation'].get('seed', 0),
            fluka=fluka,
            geant4=geant4,
            scoring=scoring,
        )

    def get_run_configs(self) -> List[Dict]:
        """Generate individual run configurations for all models."""
        runs = []

        if self.fluka.enabled:
            for lib in self.fluka.neutron_libraries:
                runs.append({
                    'code': 'fluka',
                    'model': lib,
                    'output_subdir': f'fluka/{lib}',
                })

        if self.geant4.enabled:
            for phys in self.geant4.physics_lists:
                runs.append({
                    'code': 'geant4',
                    'model': phys,
                    'output_subdir': f'geant4/{phys}',
                })

        return runs


@dataclass
class PlotConfig:
    """Configuration for a single plot type."""
    enabled: bool
    log_scale: bool = True
    show_ratio: bool = False
    output: str = ""


@dataclass
class AnalysisConfig:
    """Analysis configuration."""
    results_dir: str
    output_dir: str
    formats: List[str]
    dpi: int
    include_fluka: List[str]
    include_geant4: List[str]
    reference_code: str
    reference_model: str
    plots: Dict[str, PlotConfig]
    style: Dict

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'AnalysisConfig':
        """Load configuration from YAML file."""
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)

        plots = {}
        for name, cfg in data.get('plots', {}).items():
            plots[name] = PlotConfig(
                enabled=cfg.get('enabled', True),
                log_scale=cfg.get('log_scale', True),
                show_ratio=cfg.get('show_ratio', False),
                output=cfg.get('output', name),
            )

        return cls(
            results_dir=data['results_dir'],
            output_dir=data['output_dir'],
            formats=data.get('formats', ['png']),
            dpi=data.get('dpi', 150),
            include_fluka=data.get('include', {}).get('fluka', []),
            include_geant4=data.get('include', {}).get('geant4', []),
            reference_code=data.get('reference', {}).get('code', 'fluka'),
            reference_model=data.get('reference', {}).get('model', 'JEFF'),
            plots=plots,
            style=data.get('style', {}),
        )

    def get_models_to_analyze(self) -> List[Dict]:
        """Get list of models to include in analysis."""
        models = []
        for lib in self.include_fluka:
            models.append({'code': 'fluka', 'model': lib})
        for phys in self.include_geant4:
            models.append({'code': 'geant4', 'model': phys})
        return models


# FLUKA particle type mapping
FLUKA_PARTICLES = {
    'neutron': 'NEUTRON',
    'proton': 'PROTON',
    'electron': 'ELECTRON',
    'positron': 'POSITRON',
    'photon': 'PHOTON',
    'muon': 'MUON+',
    'muon+': 'MUON+',
    'muon-': 'MUON-',
    'pion+': 'PION+',
    'pion-': 'PION-',
}

# Geant4 particle type mapping
GEANT4_PARTICLES = {
    'neutron': 'neutron',
    'proton': 'proton',
    'electron': 'e-',
    'positron': 'e+',
    'photon': 'gamma',
    'muon': 'mu-',
    'muon+': 'mu+',
    'muon-': 'mu-',
    'pion+': 'pi+',
    'pion-': 'pi-',
}

# FLUKA neutron library SDUM codes (must be ≤8 chars)
FLUKA_NEUTRON_LIBS = {
    'JEFF': 'JEFF-3.3',   # must match run_fluka.sh (8 chars max)
    'ENDF': 'ENDFB8.0',
    'JENDL': 'JENDL4.0',
    'CENDL': 'CENDL3.1',
    'BROND': 'BROND3.1',
}


def validate_config(config: SimulationConfig) -> List[str]:
    """Validate configuration and return list of warnings/errors."""
    issues = []

    # Check particle type
    if config.particle.type.lower() not in FLUKA_PARTICLES:
        issues.append(f"Unknown particle type: {config.particle.type}")

    # Check GDML file exists
    if not os.path.exists(config.geometry_gdml):
        issues.append(f"GDML file not found: {config.geometry_gdml}")

    # Check neutron libraries
    for lib in config.fluka.neutron_libraries:
        if lib not in FLUKA_NEUTRON_LIBS:
            issues.append(f"Unknown FLUKA neutron library: {lib}")

    # Check events count
    if config.events < 1:
        issues.append("Events must be >= 1")

    return issues
