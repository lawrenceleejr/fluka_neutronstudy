#!/usr/bin/env python3
"""
Plot energy deposition from FLUKA USRBIN output.
Reads ASCII output from usbrea conversion of USRBIN binary files.

Usage:
    python3 plot_edep.py [output_directory]           # Single plot
    python3 plot_edep.py --scan                       # Energy scan mode
    python3 plot_edep.py --scan --energies 0.1,1,10   # Custom energies

If no directory specified, uses output/latest symlink.
Energy is auto-detected from run_info.txt metadata.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import os
import sys
import re
import argparse
import subprocess
import csv
from datetime import datetime


def read_run_info(output_dir):
    """Read run metadata from run_info.txt"""
    info = {}
    info_file = os.path.join(output_dir, 'run_info.txt')

    if os.path.exists(info_file):
        with open(info_file, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    info[key.strip()] = value.strip()

    return info


def read_usrbin_ascii(filename):
    """
    Read FLUKA USRBIN ASCII output from usbrea.

    FLUKA stores data as A(ix,iy,iz) where Z varies fastest.
    """
    with open(filename, 'r') as f:
        content = f.read()

    # Parse header for grid dimensions
    header_info = {}

    # X coordinate
    match = re.search(r'X coordinate: from\s+([-\d.E+]+)\s+to\s+([-\d.E+]+)\s+cm,\s+(\d+)\s+bins', content)
    if match:
        header_info['xmin'] = float(match.group(1))
        header_info['xmax'] = float(match.group(2))
        header_info['nx'] = int(match.group(3))

    # Y coordinate
    match = re.search(r'Y coordinate: from\s+([-\d.E+]+)\s+to\s+([-\d.E+]+)\s+cm,\s+(\d+)\s+bins', content)
    if match:
        header_info['ymin'] = float(match.group(1))
        header_info['ymax'] = float(match.group(2))
        header_info['ny'] = int(match.group(3))

    # Z coordinate
    match = re.search(r'Z coordinate: from\s+([-\d.E+]+)\s+to\s+([-\d.E+]+)\s+cm,\s+(\d+)\s+bins', content)
    if match:
        header_info['zmin'] = float(match.group(1))
        header_info['zmax'] = float(match.group(2))
        header_info['nz'] = int(match.group(3))

    print(f"Grid: X={header_info.get('nx')} bins [{header_info.get('xmin')}, {header_info.get('xmax')}]")
    print(f"      Y={header_info.get('ny')} bins [{header_info.get('ymin')}, {header_info.get('ymax')}]")
    print(f"      Z={header_info.get('nz')} bins [{header_info.get('zmin')}, {header_info.get('zmax')}]")

    # Find where data starts (after "accurate deposition" or similar line)
    lines = content.split('\n')
    data_start = 0
    for i, line in enumerate(lines):
        if 'accurate deposition' in line.lower() or 'data follow' in line.lower():
            data_start = i + 1
            break
        # Also look for first line that starts with scientific notation
        if i > 5 and re.match(r'\s+[-\d.E+]+', line):
            data_start = i
            break

    # Read all numeric data
    data_values = []
    for line in lines[data_start:]:
        # Extract all scientific notation numbers
        numbers = re.findall(r'[-+]?\d+\.?\d*[Ee][-+]?\d+', line)
        for num in numbers:
            try:
                data_values.append(float(num))
            except ValueError:
                continue

    print(f"Read {len(data_values)} data values")

    return np.array(data_values), header_info


def compute_total_energy(data, header, cycles=1):
    """
    Compute total energy deposition and statistical error on the mean.

    FLUKA's usbsuw merges cycles and provides mean values per primary.
    The statistical error on the mean is estimated using the spread in
    bin values and scales as 1/sqrt(cycles).

    Args:
        data: Energy deposition data array
        header: Header info with grid dimensions
        cycles: Number of FLUKA cycles (for error estimation)

    Returns:
        total: Total energy deposition (GeV/primary) - mean value
        error: Statistical error on the mean (GeV/primary)
    """
    nx = header.get('nx', 100)
    ny = header.get('ny', 1)
    nz = header.get('nz', 200)
    xmin = header.get('xmin', -100)
    xmax = header.get('xmax', 100)
    ymin = header.get('ymin', -100)
    ymax = header.get('ymax', 100)
    zmin = header.get('zmin', -5)
    zmax = header.get('zmax', 395)

    expected_size = nx * ny * nz
    if len(data) < expected_size:
        data = np.pad(data, (0, expected_size - len(data)))
    elif len(data) > expected_size:
        data = data[:expected_size]

    # Compute bin volumes (cm^3)
    dx = (xmax - xmin) / nx
    dy = (ymax - ymin) / ny
    dz = (zmax - zmin) / nz
    bin_volume = dx * dy * dz

    # Data is in GeV/cm³/primary, multiply by volume to get GeV/primary
    # This is already the mean value (averaged over all primaries by FLUKA)
    total = np.sum(data) * bin_volume

    # Estimate statistical error on the mean
    # For Monte Carlo, error scales as 1/sqrt(N) where N = cycles * primaries_per_cycle
    # Using relative standard deviation of non-zero bins as proxy for spread
    nonzero_data = data[data > 0]
    if len(nonzero_data) > 1 and total > 0:
        # Relative standard deviation of bin values
        rel_std = np.std(nonzero_data) / np.mean(nonzero_data)
        # Error on sum scales with sqrt(N_bins), error on mean scales with 1/sqrt(cycles)
        # Combined estimate: rel_error ~ rel_std / sqrt(N_bins) / sqrt(cycles)
        n_bins = len(nonzero_data)
        rel_error = rel_std / np.sqrt(n_bins) / np.sqrt(cycles)
        error = total * rel_error
    elif total > 0:
        # Fallback: assume ~10% relative error scaled by cycles
        error = total * 0.1 / np.sqrt(cycles)
    else:
        error = 0.0

    return total, error


def plot_energy_deposition(data, header, output_file='edep_xz_plot.png', energy_mev=1.0, neutron_lib='', show_plot=True, cycles=1):
    """Create energy deposition plot.

    Args:
        data: Energy deposition data array
        header: Header info with grid dimensions
        output_file: Path to save the plot
        energy_mev: Neutron energy in MeV (for title)
        neutron_lib: Neutron library name (for title)
        show_plot: Whether to display the plot interactively
        cycles: Number of FLUKA cycles (for error estimation)

    Returns:
        total_energy: Total energy deposited (GeV/primary) - mean value
        error: Statistical error on the mean (GeV/primary)
    """

    nx = header.get('nx', 100)
    ny = header.get('ny', 1)
    nz = header.get('nz', 200)
    xmin = header.get('xmin', -10)
    xmax = header.get('xmax', 10)
    zmin = header.get('zmin', -5)
    zmax = header.get('zmax', 35)

    expected_size = nx * ny * nz
    print(f"Expected {expected_size} values, got {len(data)}")

    if len(data) < expected_size:
        print("Warning: Not enough data, padding with zeros")
        data = np.pad(data, (0, expected_size - len(data)))
    elif len(data) > expected_size:
        print("Warning: Extra data, truncating")
        data = data[:expected_size]

    # FLUKA stores as A(ix, iy, iz) in Fortran column-major order
    # This means ix varies FASTEST, then iy, then iz (slowest)
    # So: A(1,1,1), A(2,1,1), ..., A(nx,1,1), A(1,1,2), A(2,1,2), ...
    # Use Fortran order in reshape to match this storage

    data_3d = data.reshape((nx, ny, nz), order='F')

    # For XZ projection with ny=1, just take the slice
    data_2d = data_3d[:, 0, :]  # Shape: (nx, nz) = (100, 200)

    print(f"2D data shape: {data_2d.shape}")
    print(f"Data range: {data_2d.min():.2e} to {data_2d.max():.2e}")

    # Create coordinate arrays for bin edges
    x = np.linspace(xmin, xmax, nx + 1)
    z = np.linspace(zmin, zmax, nz + 1)

    fig, ax = plt.subplots(figsize=(10, 8))

    # data_2d has shape (nx, nz)
    # For pcolormesh: X should be horizontal, Z should be vertical
    # pcolormesh(X, Y, C) where C[j, i] is at (X[i], Y[j])
    # So we need to transpose: C should be (nz, nx) for Z on vertical, X on horizontal
    plot_data = data_2d.T  # Now shape (nz, nx)

    # Fixed color axis limits
    vmin, vmax = 1e-12, 1e-6

    # Set floor for log scale - zeros become minimum value
    plot_data_floored = np.where(plot_data <= 0, vmin, plot_data)

    # Report actual data range for reference
    nonzero_data = plot_data[plot_data > 0]
    if len(nonzero_data) > 0:
        print(f"Data range: {nonzero_data.min():.2e} to {nonzero_data.max():.2e}")
    print(f"Plot range (fixed): {vmin:.2e} to {vmax:.2e}")

    # Use log scale
    norm = colors.LogNorm(vmin=vmin, vmax=vmax)

    im = ax.pcolormesh(x, z, plot_data_floored,
                       cmap='jet',
                       norm=norm,
                       shading='flat')

    cbar = plt.colorbar(im, ax=ax, label='Energy Deposition (GeV/cm³/primary)')

    ax.set_xlabel('X (cm)', fontsize=12)
    ax.set_ylabel('Z (cm)', fontsize=12)
    lib_str = f' [{neutron_lib}]' if neutron_lib else ''
    ax.set_title(f'Energy Deposition: {energy_mev} MeV Neutron in Borated Polyethylene{lib_str}\n(XZ Projection)',
                 fontsize=14)

    # Add neutron source indicator at center of Z range
    z_center = (zmin + zmax) / 2
    arrow_len = (zmax - zmin) * 0.05
    ax.plot(0, z_center, 'g^', markersize=15, label=f'Neutron source ({energy_mev} MeV)', zorder=10)
    ax.arrow(0, z_center + arrow_len*0.5, 0, arrow_len, head_width=2, head_length=arrow_len*0.3, fc='green', ec='green', zorder=10)

    ax.legend(loc='upper right', fontsize=10)
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Plot saved to: {output_file}")
    if show_plot:
        plt.show()
    plt.close()

    # Compute total energy deposition (mean value and error on mean)
    total_energy, error = compute_total_energy(data, header, cycles=cycles)
    return total_energy, error


def run_simulation(energy_mev, cycles=5, neutron_lib='JEFF'):
    """Run FLUKA simulation for a given energy."""
    print(f"\n{'='*60}")
    print(f"Running simulation for {energy_mev} MeV neutrons ({neutron_lib})")
    print(f"{'='*60}")

    cmd = ['./run_fluka.sh', str(cycles), str(energy_mev), neutron_lib]
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print(f"WARNING: Simulation for {energy_mev} MeV may have failed")
        return None

    # Find the output directory (most recent with this energy)
    output_base = './output'
    latest_dir = None
    latest_time = 0

    for dirname in os.listdir(output_base):
        if f'{energy_mev}MeV' in dirname and dirname != 'latest':
            dir_path = os.path.join(output_base, dirname)
            mtime = os.path.getmtime(dir_path)
            if mtime > latest_time:
                latest_time = mtime
                latest_dir = dir_path

    return latest_dir


def process_single_output(output_dir, show_plot=True):
    """Process a single output directory and return energy deposition data."""
    # Resolve symlink to actual path
    if os.path.islink(output_dir):
        link_target = os.readlink(output_dir)
        output_dir = os.path.join(os.path.dirname(output_dir), link_target)

    print(f"\nProcessing: {output_dir}")

    # Read run metadata for energy, library, and cycles
    run_info = read_run_info(output_dir)
    energy_mev = float(run_info.get('energy_mev', 1.0))
    neutron_lib = run_info.get('neutron_library', '')
    cycles = int(run_info.get('cycles', 1))

    # Look for the XZ ASCII file
    xz_file = os.path.join(output_dir, 'edep_xz.dat')

    if not os.path.exists(xz_file):
        print(f"ERROR: File not found: {xz_file}")
        return None

    data, header = read_usrbin_ascii(xz_file)

    if len(data) == 0:
        print("ERROR: No data read from file")
        return None

    # Save plot in the output directory
    plot_file = os.path.join(output_dir, 'edep_xz_plot.png')
    total_energy, error = plot_energy_deposition(
        data, header,
        output_file=plot_file,
        energy_mev=energy_mev,
        neutron_lib=neutron_lib,
        show_plot=show_plot,
        cycles=cycles
    )

    return {
        'energy_mev': energy_mev,
        'neutron_lib': neutron_lib,
        'total_edep': total_energy,
        'error': error,
        'output_dir': output_dir
    }


def plot_energy_scan_summary(results, output_file='energy_scan_summary.png', neutron_lib=''):
    """Create summary plot of total energy deposition vs neutron energy."""
    energies = [r['energy_mev'] for r in results]
    totals = [r['total_edep'] for r in results]
    errors = [r['error'] for r in results]

    fig, ax = plt.subplots(figsize=(10, 7))

    ax.errorbar(energies, totals, yerr=errors, fmt='o-', capsize=5,
                markersize=8, linewidth=2, color='blue', ecolor='red',
                label=f'Total Energy Deposition ({neutron_lib})')

    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel('Neutron Energy (MeV)', fontsize=12)
    ax.set_ylabel('Total Energy Deposited (GeV/primary)', fontsize=12)
    lib_str = f' [{neutron_lib}]' if neutron_lib else ''
    ax.set_title(f'Energy Deposition vs Neutron Energy{lib_str}\nBorated Polyethylene', fontsize=14)
    ax.grid(True, which='both', linestyle='--', alpha=0.7)
    ax.legend(loc='best', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\nSummary plot saved to: {output_file}")
    plt.show()
    plt.close()


def write_csv_results(results, output_file='energy_scan_results.csv', neutron_lib=''):
    """Write energy scan results to CSV file."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['# Energy scan results'])
        writer.writerow([f'# Neutron library: {neutron_lib}'])
        writer.writerow([f'# Generated: {datetime.now().isoformat()}'])
        writer.writerow([])
        writer.writerow(['energy_mev', 'total_edep_gev', 'stat_error_gev', 'relative_error'])

        for r in results:
            rel_error = r['error'] / r['total_edep'] if r['total_edep'] > 0 else 0
            writer.writerow([
                r['energy_mev'],
                f"{r['total_edep']:.6e}",
                f"{r['error']:.6e}",
                f"{rel_error:.4f}"
            ])

    print(f"CSV results saved to: {output_file}")


def energy_scan_mode(energies, cycles=5, neutron_lib='JEFF', run_simulations=True):
    """
    Run energy scan: simulate multiple energies and create summary plots.

    Args:
        energies: List of neutron energies in MeV
        cycles: Number of FLUKA cycles per energy
        neutron_lib: Neutron library to use (JEFF, ENDF, TENDL)
        run_simulations: If True, run FLUKA simulations; if False, use existing outputs
    """
    print("="*60)
    print("FLUKA Energy Scan Mode")
    print("="*60)
    print(f"Energies: {energies} MeV")
    print(f"Neutron library: {neutron_lib}")
    print(f"Cycles per energy: {cycles}")
    print(f"Run simulations: {run_simulations}")

    results = []

    for energy in energies:
        if run_simulations:
            output_dir = run_simulation(energy, cycles=cycles, neutron_lib=neutron_lib)
            if output_dir is None:
                print(f"Skipping {energy} MeV due to simulation failure")
                continue
        else:
            # Find existing output for this energy
            output_base = './output'
            output_dir = None
            latest_time = 0

            for dirname in os.listdir(output_base):
                if f'{energy}MeV' in dirname and neutron_lib in dirname and dirname != 'latest':
                    dir_path = os.path.join(output_base, dirname)
                    mtime = os.path.getmtime(dir_path)
                    if mtime > latest_time:
                        latest_time = mtime
                        output_dir = dir_path

            if output_dir is None:
                print(f"No existing output found for {energy} MeV, skipping")
                continue

        result = process_single_output(output_dir, show_plot=False)
        if result:
            results.append(result)
            print(f"  {energy} MeV: Total E_dep = {result['total_edep']:.4e} ± {result['error']:.4e} GeV/primary")

    if not results:
        print("ERROR: No results to plot")
        return

    # Sort results by energy
    results.sort(key=lambda x: x['energy_mev'])

    # Create timestamp for output files
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    scan_dir = f'./output/scan_{timestamp}_{neutron_lib}'
    os.makedirs(scan_dir, exist_ok=True)

    # Write CSV results
    csv_file = os.path.join(scan_dir, f'energy_scan_{neutron_lib}.csv')
    write_csv_results(results, csv_file, neutron_lib)

    # Create summary plot
    summary_file = os.path.join(scan_dir, f'energy_scan_summary_{neutron_lib}.png')
    plot_energy_scan_summary(results, summary_file, neutron_lib)

    print(f"\nEnergy scan complete. Results in: {scan_dir}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Plot energy deposition from FLUKA USRBIN output',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 plot_edep.py                           # Plot latest output
  python3 plot_edep.py output/20240101_120000    # Plot specific output
  python3 plot_edep.py --scan                    # Run energy scan (default energies)
  python3 plot_edep.py --scan --energies 0.1,1,10  # Custom energies
  python3 plot_edep.py --scan --no-run           # Plot existing outputs only
        """
    )

    parser.add_argument('output_dir', nargs='?', default='./output/latest',
                        help='Output directory to plot (default: ./output/latest)')
    parser.add_argument('--scan', action='store_true',
                        help='Enable energy scan mode')
    parser.add_argument('--energies', type=str, default='0.01,0.1,1,10,100,1000',
                        help='Comma-separated list of energies in MeV (default: 0.01,0.1,1,10,100,1000)')
    parser.add_argument('--cycles', type=int, default=5,
                        help='Number of FLUKA cycles per energy (default: 5)')
    parser.add_argument('--library', type=str, default='JEFF',
                        choices=['JEFF', 'ENDF', 'TENDL'],
                        help='Neutron library to use (default: JEFF)')
    parser.add_argument('--no-run', action='store_true',
                        help='Do not run simulations, use existing outputs only')

    args = parser.parse_args()

    if args.scan:
        # Energy scan mode
        energies = [float(e.strip()) for e in args.energies.split(',')]
        energy_scan_mode(
            energies,
            cycles=args.cycles,
            neutron_lib=args.library,
            run_simulations=not args.no_run
        )
    else:
        # Single plot mode
        output_dir = args.output_dir

        # Resolve symlink to actual path
        if os.path.islink(output_dir):
            link_target = os.readlink(output_dir)
            output_dir = os.path.join(os.path.dirname(output_dir), link_target)

        print("FLUKA Energy Deposition Visualization")
        print("=" * 50)
        print(f"Output directory: {output_dir}")

        # Read run metadata for energy, library, and cycles
        run_info = read_run_info(output_dir)
        energy_mev = float(run_info.get('energy_mev', 1.0))
        neutron_lib = run_info.get('neutron_library', '')
        cycles = int(run_info.get('cycles', 1))
        print(f"Neutron energy: {energy_mev} MeV (from metadata)")
        print(f"Cycles: {cycles}")
        if neutron_lib:
            print(f"Neutron library: {neutron_lib}")

        # Look for the XZ ASCII file
        xz_file = os.path.join(output_dir, 'edep_xz.dat')

        if os.path.exists(xz_file):
            print(f"Reading: {xz_file}")
            data, header = read_usrbin_ascii(xz_file)

            if len(data) > 0:
                # Save plot in the output directory
                plot_file = os.path.join(output_dir, 'edep_xz_plot.png')
                total, error = plot_energy_deposition(
                    data, header,
                    output_file=plot_file,
                    energy_mev=energy_mev,
                    neutron_lib=neutron_lib,
                    cycles=cycles
                )
                print(f"\nTotal energy deposition (mean): {total:.4e} ± {error:.4e} GeV/primary")
            else:
                print("ERROR: No data read from file")
        else:
            print(f"ERROR: File not found: {xz_file}")
            print("Run the FLUKA simulation first with: ./run_fluka.sh")


if __name__ == '__main__':
    main()
