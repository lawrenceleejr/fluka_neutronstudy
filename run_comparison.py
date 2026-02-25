#!/usr/bin/env python3
"""
Run FLUKA vs Geant4 comparison simulations.

Usage:
    python run_comparison.py --config config/simulation_config.yaml
    python run_comparison.py --config config/simulation_config.yaml --fluka-only
    python run_comparison.py --config config/simulation_config.yaml --parallel
"""

import argparse
import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config_parser import SimulationConfig, validate_config
from src.runner import ComparisonRunner


def main():
    parser = argparse.ArgumentParser(
        description="Run FLUKA vs Geant4 comparison simulations"
    )
    parser.add_argument(
        '--config', '-c',
        default='config/simulation_config.yaml',
        help='Path to simulation configuration YAML'
    )
    parser.add_argument(
        '--fluka-only',
        action='store_true',
        help='Run only FLUKA simulations'
    )
    parser.add_argument(
        '--geant4-only',
        action='store_true',
        help='Run only Geant4 simulations'
    )
    parser.add_argument(
        '--models',
        type=str,
        help='Comma-separated list of specific models to run'
    )
    parser.add_argument(
        '--flugg',
        action='store_true',
        help='Use FLUGG for FLUKA (external GDML geometry)'
    )
    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Run simulations in parallel'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of parallel workers (default: 4)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be run without executing'
    )

    args = parser.parse_args()

    # Load configuration
    print(f"Loading configuration from {args.config}")
    config = SimulationConfig.from_yaml(args.config)

    # Validate
    issues = validate_config(config)
    if issues:
        print("Configuration issues:")
        for issue in issues:
            print(f"  - {issue}")
        if any("not found" in i for i in issues):
            sys.exit(1)

    # Determine which models to run
    fluka_models = []
    geant4_models = []

    if args.models:
        requested = [m.strip() for m in args.models.split(',')]
        for m in requested:
            if m in config.fluka.neutron_libraries:
                fluka_models.append(m)
            elif m in config.geant4.physics_lists:
                geant4_models.append(m)
            else:
                print(f"Warning: Unknown model '{m}'")
    else:
        if not args.geant4_only:
            fluka_models = config.fluka.neutron_libraries if config.fluka.enabled else []
        if not args.fluka_only:
            geant4_models = config.geant4.physics_lists if config.geant4.enabled else []

    # Summary
    print("\nSimulation plan:")
    print(f"  Events: {config.events}")
    print(f"  Geometry: {config.geometry_gdml}")
    print(f"  Output: {config.output_dir}")
    if fluka_models:
        print(f"  FLUKA models: {', '.join(fluka_models)}")
    if geant4_models:
        print(f"  Geant4 models: {', '.join(geant4_models)}")
    print(f"  Mode: {'FLUGG' if args.flugg else 'Native'}")
    print(f"  Parallel: {args.parallel}")
    print()

    if args.dry_run:
        print("Dry run - not executing simulations")
        return

    # Create runner and execute
    runner = ComparisonRunner(config, use_flugg=args.flugg)

    print("Starting simulations...")
    results = runner.run_all(
        fluka_models=fluka_models if fluka_models else None,
        geant4_models=geant4_models if geant4_models else None,
        parallel=args.parallel,
        max_workers=args.workers,
    )

    # Write summary
    summary_file = os.path.join(config.output_dir, 'run_summary.csv')
    os.makedirs(config.output_dir, exist_ok=True)
    runner.generate_summary(summary_file)

    # Print results
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)

    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful

    for r in results:
        status = "OK" if r.success else "FAILED"
        print(f"  {r.code}/{r.model}: {status} ({r.runtime_seconds:.1f}s)")
        if r.error_message:
            print(f"    Error: {r.error_message[:100]}")

    print()
    print(f"Total: {successful} successful, {failed} failed")
    print(f"Summary written to: {summary_file}")

    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
