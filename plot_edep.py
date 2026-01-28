#!/usr/bin/env python3
"""
Plot energy deposition from FLUKA USRBIN output.
Reads ASCII output from usbrea conversion of USRBIN binary files.

Usage:
    python3 plot_edep.py [output_directory]

If no directory specified, uses output/latest symlink.
Energy is auto-detected from run_info.txt metadata.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import os
import sys
import re


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


def plot_energy_deposition(data, header, output_file='edep_xz_plot.png', energy_mev=1.0, neutron_lib=''):
    """Create energy deposition plot."""

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

    # Find data range for non-zero values
    nonzero_data = plot_data[plot_data > 0]
    if len(nonzero_data) > 0:
        vmin = nonzero_data.min()
        vmax = nonzero_data.max()
    else:
        vmin, vmax = 1e-12, 1e-6

    # Set floor for log scale - zeros become minimum value
    vmin = max(vmin, vmax / 1e6)
    plot_data_floored = np.where(plot_data <= 0, vmin, plot_data)

    print(f"Plot range: {vmin:.2e} to {vmax:.2e}")

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
    plt.show()


def main():
    # Parse command line arguments
    # Usage: plot_edep.py [output_directory]

    # Default to output/latest symlink
    if len(sys.argv) > 1:
        output_dir = sys.argv[1]
    else:
        output_dir = './output/latest'

    # Resolve symlink to actual path
    if os.path.islink(output_dir):
        link_target = os.readlink(output_dir)
        output_dir = os.path.join(os.path.dirname(output_dir), link_target)

    print("FLUKA Energy Deposition Visualization")
    print("=" * 50)
    print(f"Output directory: {output_dir}")

    # Read run metadata for energy and library
    run_info = read_run_info(output_dir)
    energy_mev = float(run_info.get('energy_mev', 1.0))
    neutron_lib = run_info.get('neutron_library', '')
    print(f"Neutron energy: {energy_mev} MeV (from metadata)")
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
            plot_energy_deposition(data, header, output_file=plot_file, energy_mev=energy_mev, neutron_lib=neutron_lib)
        else:
            print("ERROR: No data read from file")
    else:
        print(f"ERROR: File not found: {xz_file}")
        print("Run the FLUKA simulation first with: ./run_fluka.sh")


if __name__ == '__main__':
    main()
