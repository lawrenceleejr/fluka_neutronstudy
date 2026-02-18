#!/usr/bin/env python3
"""
Analyze and plot FLUKA vs Geant4 comparison results.

Usage:
    python analyze_results.py --config config/analysis_config.yaml
    python analyze_results.py --results output/scan_results --reference fluka/JEFF
"""

import argparse
import os
import sys
import glob
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config_parser import AnalysisConfig


def read_edep_profile(filepath: str) -> Tuple[np.ndarray, np.ndarray]:
    """Read energy deposition profile from dat file."""
    data = np.loadtxt(filepath, comments='#')
    if data.ndim == 1:
        return np.array([0.5]), np.array([data[0]])
    return data[:, 0], data[:, 1]


def read_neutron_spectrum(filepath: str) -> Tuple[np.ndarray, np.ndarray]:
    """Read neutron spectrum from dat file."""
    data = np.loadtxt(filepath, comments='#')
    if data.ndim == 1:
        return np.array([1.0]), np.array([data[0]])
    return data[:, 0], data[:, 1]


def discover_results(results_dir: str) -> Dict[str, Dict[str, str]]:
    """
    Discover available simulation results.

    Returns:
        Dict mapping code/model to output directory
    """
    results = {'fluka': {}, 'geant4': {}}

    # FLUKA results
    fluka_dirs = glob.glob(os.path.join(results_dir, 'fluka', '*'))
    for d in fluka_dirs:
        if os.path.isdir(d):
            model = os.path.basename(d)
            results['fluka'][model] = d

    # Geant4 results
    geant4_dirs = glob.glob(os.path.join(results_dir, 'geant4', '*'))
    for d in geant4_dirs:
        if os.path.isdir(d):
            model = os.path.basename(d)
            results['geant4'][model] = d

    return results


def load_all_edep(
    results: Dict[str, Dict[str, str]]
) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Load energy deposition profiles for all results."""
    data = {}

    for code in ['fluka', 'geant4']:
        for model, output_dir in results[code].items():
            # Look for edep file
            edep_file = os.path.join(output_dir, 'edep_profile.dat')
            if not os.path.exists(edep_file):
                # Try FLUKA format
                edep_file = os.path.join(output_dir, 'input001_21.dat')
            if os.path.exists(edep_file):
                try:
                    z, edep = read_edep_profile(edep_file)
                    data[f"{code}/{model}"] = (z, edep)
                except Exception as e:
                    print(f"Warning: Could not read {edep_file}: {e}")

    return data


def load_all_spectra(
    results: Dict[str, Dict[str, str]]
) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Load neutron spectra for all results."""
    data = {}

    for code in ['fluka', 'geant4']:
        for model, output_dir in results[code].items():
            spec_file = os.path.join(output_dir, 'neutron_spectrum.dat')
            if not os.path.exists(spec_file):
                # Try FLUKA format
                spec_file = os.path.join(output_dir, 'input001_23.dat')
            if os.path.exists(spec_file):
                try:
                    e, counts = read_neutron_spectrum(spec_file)
                    data[f"{code}/{model}"] = (e, counts)
                except Exception as e:
                    print(f"Warning: Could not read {spec_file}: {e}")

    return data


def plot_edep_comparison(
    edep_data: Dict[str, Tuple[np.ndarray, np.ndarray]],
    reference: str,
    output_path: str,
    log_scale: bool = True,
    show_ratio: bool = True,
    colors: Optional[Dict] = None,
    linestyles: Optional[Dict] = None,
):
    """Plot energy deposition comparison with optional ratio panel."""
    if not edep_data:
        print("No energy deposition data to plot")
        return

    if show_ratio and reference in edep_data:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10),
                                        gridspec_kw={'height_ratios': [3, 1]},
                                        sharex=True)
    else:
        fig, ax1 = plt.subplots(1, 1, figsize=(10, 6))
        ax2 = None

    ref_z, ref_edep = edep_data.get(reference, (None, None))

    for label, (z, edep) in sorted(edep_data.items()):
        code = label.split('/')[0]
        model = label.split('/')[1]

        # Get style
        color = None
        if colors and code in colors and model in colors[code]:
            color = colors[code][model]

        ls = '-' if code == 'fluka' else '--'
        if linestyles and code in linestyles:
            ls = linestyles[code]

        # Plot main data
        ax1.plot(z, edep, label=label, color=color, linestyle=ls, linewidth=1.5)

        # Plot ratio if reference exists
        if ax2 is not None and ref_edep is not None and label != reference:
            # Interpolate to reference z-grid if needed
            if len(z) == len(ref_z) and np.allclose(z, ref_z):
                ratio = np.divide(edep, ref_edep, out=np.ones_like(edep),
                                 where=ref_edep != 0)
            else:
                ratio = np.interp(ref_z, z, edep) / ref_edep
                ratio = np.where(ref_edep != 0, ratio, 1.0)
            ax2.plot(ref_z, ratio, label=label, color=color, linestyle=ls,
                    linewidth=1.5)

    ax1.set_ylabel('Energy Deposition [GeV/cm³/primary]')
    if log_scale:
        ax1.set_yscale('log')
    ax1.legend(loc='best', fontsize=8, ncol=2)
    ax1.grid(True, alpha=0.3)
    ax1.set_title('Energy Deposition Profile Comparison')

    if ax2 is not None:
        ax2.set_xlabel('z [cm]')
        ax2.set_ylabel(f'Ratio to {reference}')
        ax2.axhline(y=1.0, color='gray', linestyle='-', linewidth=0.5)
        ax2.axhline(y=0.9, color='gray', linestyle='--', linewidth=0.5)
        ax2.axhline(y=1.1, color='gray', linestyle='--', linewidth=0.5)
        ax2.set_ylim(0.5, 1.5)
        ax2.grid(True, alpha=0.3)
    else:
        ax1.set_xlabel('z [cm]')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def plot_spectrum_comparison(
    spectrum_data: Dict[str, Tuple[np.ndarray, np.ndarray]],
    reference: str,
    output_path: str,
    log_scale: bool = True,
    show_ratio: bool = True,
    colors: Optional[Dict] = None,
    linestyles: Optional[Dict] = None,
):
    """Plot neutron spectrum comparison with optional ratio panel."""
    if not spectrum_data:
        print("No spectrum data to plot")
        return

    if show_ratio and reference in spectrum_data:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10),
                                        gridspec_kw={'height_ratios': [3, 1]},
                                        sharex=True)
    else:
        fig, ax1 = plt.subplots(1, 1, figsize=(10, 6))
        ax2 = None

    ref_e, ref_counts = spectrum_data.get(reference, (None, None))

    for label, (e, counts) in sorted(spectrum_data.items()):
        code = label.split('/')[0]
        model = label.split('/')[1]

        color = None
        if colors and code in colors and model in colors[code]:
            color = colors[code][model]

        ls = '-' if code == 'fluka' else '--'
        if linestyles and code in linestyles:
            ls = linestyles[code]

        ax1.step(e, counts, label=label, color=color, linestyle=ls,
                 linewidth=1.5, where='mid')

        if ax2 is not None and ref_counts is not None and label != reference:
            ratio = np.divide(counts, ref_counts, out=np.ones_like(counts),
                             where=ref_counts != 0)
            ax2.step(ref_e, ratio, label=label, color=color, linestyle=ls,
                    linewidth=1.5, where='mid')

    ax1.set_ylabel('Neutron count')
    ax1.set_xscale('log')
    if log_scale:
        ax1.set_yscale('log')
    ax1.legend(loc='best', fontsize=8, ncol=2)
    ax1.grid(True, alpha=0.3)
    ax1.set_title('Neutron Exit Spectrum Comparison')

    if ax2 is not None:
        ax2.set_xlabel('Energy [GeV]')
        ax2.set_ylabel(f'Ratio to {reference}')
        ax2.set_xscale('log')
        ax2.axhline(y=1.0, color='gray', linestyle='-', linewidth=0.5)
        ax2.axhline(y=0.9, color='gray', linestyle='--', linewidth=0.5)
        ax2.axhline(y=1.1, color='gray', linestyle='--', linewidth=0.5)
        ax2.set_ylim(0.5, 1.5)
        ax2.grid(True, alpha=0.3)
    else:
        ax1.set_xlabel('Energy [GeV]')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def plot_total_edep_bar(
    edep_data: Dict[str, Tuple[np.ndarray, np.ndarray]],
    output_path: str,
):
    """Plot bar chart of total energy deposited by each model."""
    if not edep_data:
        print("No energy deposition data to plot")
        return

    labels = []
    totals = []
    colors_list = []

    for label, (z, edep) in sorted(edep_data.items()):
        code = label.split('/')[0]
        dz = z[1] - z[0] if len(z) > 1 else 1.0
        total = np.sum(edep) * dz
        labels.append(label)
        totals.append(total)
        colors_list.append('#1f77b4' if code == 'fluka' else '#ff7f0e')

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(labels))
    bars = ax.bar(x, totals, color=colors_list)

    ax.set_xlabel('Model')
    ax.set_ylabel('Total Energy Deposited [GeV/primary]')
    ax.set_title('Total Energy Deposition Comparison')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right')

    # Add value labels
    for bar, val in zip(bars, totals):
        ax.annotate(f'{val:.2e}',
                   xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                   xytext=(0, 3), textcoords='offset points',
                   ha='center', va='bottom', fontsize=8, rotation=45)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def plot_model_spread(
    edep_data: Dict[str, Tuple[np.ndarray, np.ndarray]],
    output_path: str,
):
    """Plot model spread (min/max envelope) for FLUKA and Geant4."""
    if not edep_data:
        print("No energy deposition data to plot")
        return

    # Separate by code
    fluka_data = {k: v for k, v in edep_data.items() if k.startswith('fluka/')}
    geant4_data = {k: v for k, v in edep_data.items() if k.startswith('geant4/')}

    fig, ax = plt.subplots(figsize=(10, 6))

    # Get common z-grid
    z_grid = None
    for _, (z, _) in edep_data.items():
        z_grid = z
        break

    if z_grid is None:
        print("No data for model spread plot")
        return

    # FLUKA envelope
    if fluka_data:
        all_edep = np.array([np.interp(z_grid, z, edep) for _, (z, edep) in fluka_data.items()])
        fluka_mean = np.mean(all_edep, axis=0)
        fluka_min = np.min(all_edep, axis=0)
        fluka_max = np.max(all_edep, axis=0)

        ax.fill_between(z_grid, fluka_min, fluka_max, alpha=0.3, color='blue',
                       label='FLUKA spread')
        ax.plot(z_grid, fluka_mean, 'b-', linewidth=2, label='FLUKA mean')

    # Geant4 envelope
    if geant4_data:
        all_edep = np.array([np.interp(z_grid, z, edep) for _, (z, edep) in geant4_data.items()])
        g4_mean = np.mean(all_edep, axis=0)
        g4_min = np.min(all_edep, axis=0)
        g4_max = np.max(all_edep, axis=0)

        ax.fill_between(z_grid, g4_min, g4_max, alpha=0.3, color='orange',
                       label='Geant4 spread')
        ax.plot(z_grid, g4_mean, color='orange', linestyle='--', linewidth=2,
               label='Geant4 mean')

    ax.set_xlabel('z [cm]')
    ax.set_ylabel('Energy Deposition [GeV/cm³/primary]')
    ax.set_yscale('log')
    ax.set_title('Model Spread Comparison: FLUKA vs Geant4')
    ax.legend(loc='best')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze FLUKA vs Geant4 comparison results"
    )
    parser.add_argument(
        '--config', '-c',
        default='config/analysis_config.yaml',
        help='Path to analysis configuration YAML'
    )
    parser.add_argument(
        '--results', '-r',
        help='Results directory (overrides config)'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output directory (overrides config)'
    )
    parser.add_argument(
        '--reference',
        help='Reference model for ratios (e.g., fluka/JEFF)'
    )
    parser.add_argument(
        '--formats',
        type=str,
        default='png',
        help='Output formats (comma-separated)'
    )

    args = parser.parse_args()

    # Load configuration
    if os.path.exists(args.config):
        print(f"Loading configuration from {args.config}")
        config = AnalysisConfig.from_yaml(args.config)
    else:
        print("No config file found, using defaults")
        config = None

    # Override with command line args
    results_dir = args.results or (config.results_dir if config else 'output/scan_results')
    output_dir = args.output or (config.output_dir if config else 'output/analysis')
    reference = args.reference or (f"{config.reference_code}/{config.reference_model}" if config else 'fluka/JEFF')
    formats = args.formats.split(',')

    os.makedirs(output_dir, exist_ok=True)

    # Discover results
    print(f"Scanning results in: {results_dir}")
    results = discover_results(results_dir)

    n_fluka = len(results['fluka'])
    n_geant4 = len(results['geant4'])
    print(f"Found: {n_fluka} FLUKA models, {n_geant4} Geant4 models")

    if n_fluka == 0 and n_geant4 == 0:
        print("No results found!")
        sys.exit(1)

    # Load data
    print("\nLoading data...")
    edep_data = load_all_edep(results)
    spectrum_data = load_all_spectra(results)

    print(f"Loaded {len(edep_data)} energy deposition profiles")
    print(f"Loaded {len(spectrum_data)} neutron spectra")

    # Get style from config
    colors = config.style.get('colors', {}) if config else {}
    linestyles = config.style.get('linestyles', {}) if config else {}

    # Generate plots
    print("\nGenerating plots...")

    for fmt in formats:
        # Energy deposition profile
        plot_edep_comparison(
            edep_data, reference,
            os.path.join(output_dir, f'edep_profile_z.{fmt}'),
            log_scale=True, show_ratio=True,
            colors=colors, linestyles=linestyles,
        )

        # Neutron spectrum
        plot_spectrum_comparison(
            spectrum_data, reference,
            os.path.join(output_dir, f'neutron_spectrum.{fmt}'),
            log_scale=True, show_ratio=True,
            colors=colors, linestyles=linestyles,
        )

        # Total energy bar chart
        plot_total_edep_bar(
            edep_data,
            os.path.join(output_dir, f'total_edep_comparison.{fmt}'),
        )

        # Model spread
        plot_model_spread(
            edep_data,
            os.path.join(output_dir, f'model_spread.{fmt}'),
        )

    print(f"\nAnalysis complete. Results in: {output_dir}")


if __name__ == '__main__':
    main()
