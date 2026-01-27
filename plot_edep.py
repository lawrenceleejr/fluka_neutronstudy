#!/usr/bin/env python3
"""
Plot energy deposition from FLUKA USRBIN output.
Reads ASCII output from usbrea conversion of USRBIN binary files.

Usage:
    python3 plot_edep.py [output_directory]
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import os
import sys
import struct
import re


def read_usrbin_ascii(filename):
    """
    Read FLUKA USRBIN ASCII output from usbrea.

    Returns:
        dict with keys: data, xbins, ybins, zbins, xmin, xmax, ymin, ymax, zmin, zmax
    """
    with open(filename, 'r') as f:
        lines = f.readlines()

    # Parse header information
    header_info = {}
    data_start = 0

    for i, line in enumerate(lines):
        if 'X coordinate' in line or 'x coordinate' in line.lower():
            # Parse: from  -10.000 to   10.000 cm,  100 bins
            match = re.search(r'from\s+([-\d.]+)\s+to\s+([-\d.]+).*?(\d+)\s+bin', line, re.IGNORECASE)
            if match:
                header_info['xmin'] = float(match.group(1))
                header_info['xmax'] = float(match.group(2))
                header_info['xbins'] = int(match.group(3))
        elif 'Y coordinate' in line or 'y coordinate' in line.lower():
            match = re.search(r'from\s+([-\d.]+)\s+to\s+([-\d.]+).*?(\d+)\s+bin', line, re.IGNORECASE)
            if match:
                header_info['ymin'] = float(match.group(1))
                header_info['ymax'] = float(match.group(2))
                header_info['ybins'] = int(match.group(3))
        elif 'Z coordinate' in line or 'z coordinate' in line.lower():
            match = re.search(r'from\s+([-\d.]+)\s+to\s+([-\d.]+).*?(\d+)\s+bin', line, re.IGNORECASE)
            if match:
                header_info['zmin'] = float(match.group(1))
                header_info['zmax'] = float(match.group(2))
                header_info['zbins'] = int(match.group(3))

        # Find where data starts (after all header lines)
        # Data lines typically start with numbers
        if i > 5:  # Skip first few lines
            parts = line.strip().split()
            if len(parts) > 0:
                try:
                    float(parts[0])
                    data_start = i
                    break
                except ValueError:
                    continue

    # Read data values
    data_values = []
    for line in lines[data_start:]:
        parts = line.strip().split()
        for val in parts:
            try:
                data_values.append(float(val))
            except ValueError:
                continue

    data = np.array(data_values)

    return {
        'data': data,
        **header_info
    }


def read_usrbin_binary(filename):
    """
    Read FLUKA USRBIN binary output directly.
    FLUKA binary format with Fortran record markers.
    """
    with open(filename, 'rb') as f:
        content = f.read()

    # FLUKA binary files have Fortran record markers
    # Format: 4-byte length, data, 4-byte length
    # This is a simplified reader - may need adjustment for specific FLUKA version

    # Skip to data section (after headers)
    # For now, return None and fall back to ASCII
    return None


def read_fort_file(filename, nx=100, ny=1, nz=200,
                   xmin=-10, xmax=10, ymin=-10, ymax=10, zmin=-5, zmax=35):
    """
    Read raw FLUKA fort.XX binary file.
    Uses default geometry parameters from the input file.
    """
    try:
        with open(filename, 'rb') as f:
            content = f.read()

        # Try to find the data section (skip Fortran headers)
        # FLUKA USRBIN binary has header records followed by data

        # Each Fortran record: 4-byte size, data, 4-byte size
        # Try different offsets to find float data

        for offset in range(0, min(1000, len(content)), 4):
            try:
                # Try reading as floats
                remaining = content[offset:]
                n_expected = nx * ny * nz
                if len(remaining) >= n_expected * 4:
                    data = struct.unpack(f'{n_expected}f', remaining[:n_expected*4])
                    data = np.array(data)

                    # Check if data looks reasonable (not all zeros or NaN)
                    if np.any(data != 0) and np.all(np.isfinite(data)):
                        return {
                            'data': data,
                            'xmin': xmin, 'xmax': xmax, 'xbins': nx,
                            'ymin': ymin, 'ymax': ymax, 'ybins': ny,
                            'zmin': zmin, 'zmax': zmax, 'zbins': nz
                        }
            except:
                continue

        return None
    except Exception as e:
        print(f"Error reading binary file: {e}")
        return None


def find_output_files(output_dir):
    """Find USRBIN output files in the directory."""
    files = {}

    # Look for ASCII files first
    for ext in ['.dat', '.txt', '.asc']:
        for name in ['edep_xz', 'EDEP-XZ', 'usrbin21']:
            path = os.path.join(output_dir, f'{name}{ext}')
            if os.path.exists(path):
                files['xz_ascii'] = path
                break

    # Look for binary files
    for name in ['edep_xz.bnn', 'neutron_bpe001_fort.21', 'fort.21']:
        path = os.path.join(output_dir, name)
        if os.path.exists(path):
            files['xz_binary'] = path
            break

    # Look in subdirectories
    for item in os.listdir(output_dir):
        item_path = os.path.join(output_dir, item)
        if os.path.isfile(item_path):
            if '_fort.21' in item or 'fort.21' in item:
                files['xz_binary'] = item_path
            elif item.endswith('.dat') and 'xz' in item.lower():
                files['xz_ascii'] = item_path

    return files


def create_2d_grid(result):
    """Create 2D XZ grid from USRBIN data."""
    nx = result.get('xbins', 100)
    ny = result.get('ybins', 1)
    nz = result.get('zbins', 200)

    data = result['data']

    # Reshape based on FLUKA ordering (Z varies fastest, then Y, then X)
    expected_size = nx * ny * nz
    if len(data) != expected_size:
        print(f"Warning: data size {len(data)} != expected {expected_size}")
        # Try to reshape anyway
        if len(data) > expected_size:
            data = data[:expected_size]
        else:
            data = np.pad(data, (0, expected_size - len(data)))

    # FLUKA stores data as (nx, ny, nz) with z varying fastest
    data_3d = data.reshape((nx, ny, nz))

    # For XZ projection, sum or take slice over Y
    if ny > 1:
        data_2d = np.sum(data_3d, axis=1)
    else:
        data_2d = data_3d[:, 0, :]

    return data_2d, result


def plot_energy_deposition(data_2d, params, output_file='edep_xz_plot.png'):
    """Create energy deposition plot."""

    xmin = params.get('xmin', -10)
    xmax = params.get('xmax', 10)
    zmin = params.get('zmin', -5)
    zmax = params.get('zmax', 35)

    fig, ax = plt.subplots(figsize=(10, 8))

    # Create coordinate arrays
    x = np.linspace(xmin, xmax, data_2d.shape[0])
    z = np.linspace(zmin, zmax, data_2d.shape[1])

    # Transpose for correct orientation (X on horizontal, Z on vertical)
    plot_data = data_2d.T

    # Handle zeros for log scale
    plot_data_masked = np.ma.masked_where(plot_data <= 0, plot_data)

    # Use log scale if data spans multiple orders of magnitude
    vmin = plot_data_masked.min() if plot_data_masked.min() > 0 else 1e-10
    vmax = plot_data_masked.max()

    if vmax / vmin > 100:
        norm = colors.LogNorm(vmin=max(vmin, vmax/1e6), vmax=vmax)
    else:
        norm = colors.Normalize(vmin=0, vmax=vmax)

    im = ax.pcolormesh(x, z, plot_data_masked,
                        cmap='hot',
                        norm=norm,
                        shading='auto')

    cbar = plt.colorbar(im, ax=ax, label='Energy Deposition (GeV/cm³/primary)')

    ax.set_xlabel('X (cm)', fontsize=12)
    ax.set_ylabel('Z (cm)', fontsize=12)
    ax.set_title('Energy Deposition: 1 MeV Neutron in Borated Polyethylene\n(XZ Projection)',
                 fontsize=14)

    # Add neutron source indicator
    ax.plot(0, 0, 'g^', markersize=15, label='Neutron source (1 MeV)')
    ax.arrow(0, 0, 0, 5, head_width=0.5, head_length=0.5, fc='green', ec='green')

    # Add material boundary indicator
    ax.axhline(y=-5, color='white', linestyle='--', linewidth=1, alpha=0.7, label='BPE block boundary')
    ax.axhline(y=35, color='white', linestyle='--', linewidth=1, alpha=0.7)
    ax.axvline(x=-10, color='white', linestyle='--', linewidth=1, alpha=0.7)
    ax.axvline(x=10, color='white', linestyle='--', linewidth=1, alpha=0.7)

    ax.legend(loc='upper right', fontsize=10)
    ax.set_aspect('equal')

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Plot saved to: {output_file}")
    plt.show()


def create_sample_data():
    """Create sample data for testing the plotting script."""
    print("Creating sample data for demonstration...")

    # Simulation parameters
    nx, nz = 100, 200
    xmin, xmax = -10, 10
    zmin, zmax = -5, 35

    # Create coordinate grids
    x = np.linspace(xmin, xmax, nx)
    z = np.linspace(zmin, zmax, nz)
    X, Z = np.meshgrid(x, z, indexing='ij')

    # Simulate neutron energy deposition pattern
    # Neutron starts at (0,0,0) going in +z direction
    # Energy deposition follows rough exponential with some scattering

    # Distance from beam axis
    r = np.sqrt(X**2)

    # Depth in material (z=0 is where neutron starts)
    depth = Z

    # Model: exponential attenuation with Gaussian lateral spread
    # Mean free path in BPE for 1 MeV neutrons ~ few cm
    lambda_mfp = 3.0  # cm
    sigma_spread = 2.0  # cm lateral spread

    # Mask for inside material only
    inside = (Z >= -5) & (Z <= 35) & (np.abs(X) <= 10)

    data = np.zeros_like(X)

    # Main beam deposition
    data = np.exp(-depth / lambda_mfp) * np.exp(-r**2 / (2 * sigma_spread**2))

    # Add some capture events (localized hot spots)
    np.random.seed(42)
    for _ in range(20):
        cx = np.random.uniform(-5, 5)
        cz = np.random.uniform(0, 20)
        cr = 1.5
        capture = np.exp(-((X - cx)**2 + (Z - cz)**2) / (2 * cr**2))
        data += 0.3 * capture

    # Apply material mask
    data[~inside] = 0
    data[data < 0] = 0

    # Normalize
    data = data / data.max() * 1e-6  # Typical FLUKA units

    return data, {
        'xmin': xmin, 'xmax': xmax, 'xbins': nx,
        'ymin': -10, 'ymax': 10, 'ybins': 1,
        'zmin': zmin, 'zmax': zmax, 'zbins': nz
    }


def main():
    # Determine output directory
    if len(sys.argv) > 1:
        output_dir = sys.argv[1]
    else:
        output_dir = './output'

    print("FLUKA Energy Deposition Visualization")
    print("=" * 50)

    # Try to find and read output files
    data_2d = None
    params = None

    if os.path.exists(output_dir):
        print(f"Looking for output files in: {output_dir}")
        files = find_output_files(output_dir)

        if 'xz_ascii' in files:
            print(f"Reading ASCII file: {files['xz_ascii']}")
            try:
                result = read_usrbin_ascii(files['xz_ascii'])
                if result and len(result['data']) > 0:
                    data_2d, params = create_2d_grid(result)
            except Exception as e:
                print(f"Error reading ASCII: {e}")

        if data_2d is None and 'xz_binary' in files:
            print(f"Trying binary file: {files['xz_binary']}")
            try:
                result = read_fort_file(files['xz_binary'])
                if result:
                    data_2d, params = create_2d_grid(result)
            except Exception as e:
                print(f"Error reading binary: {e}")

    # If no data found, create sample data
    if data_2d is None:
        print("\nNo FLUKA output found. Creating sample demonstration plot.")
        print("To use real data, run the FLUKA simulation first with:")
        print("  ./run_fluka.sh")
        print("")
        data_2d, params = create_sample_data()

    # Create the plot
    plot_energy_deposition(data_2d, params)


if __name__ == '__main__':
    main()
