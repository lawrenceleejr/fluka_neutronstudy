"""
Docker execution runner for FLUKA and Geant4 simulations.

Handles container management, volume mounting, and result collection.
"""

import os
import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config_parser import SimulationConfig


# Docker image names
FLUGG_IMAGE = "flugg:latest"
GEANT4_IMAGE = "ghcr.io/kalradaisy/geant4muc:dev-CI"
FLUKA_IMAGE = "fluka:ggi"


@dataclass
class RunResult:
    """Result of a simulation run."""
    code: str           # 'fluka' or 'geant4'
    model: str          # neutron library or physics list
    success: bool
    output_dir: str
    runtime_seconds: float
    error_message: Optional[str] = None


def run_command(cmd: List[str], cwd: Optional[str] = None,
                timeout: int = 3600) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds"
    except Exception as e:
        return -1, "", str(e)


def run_fluka_native(
    config: SimulationConfig,
    neutron_library: str,
    input_file: str,
    output_dir: str,
) -> RunResult:
    """
    Run FLUKA simulation with native geometry in Docker.

    Args:
        config: Simulation configuration
        neutron_library: Neutron library name
        input_file: Path to FLUKA input file
        output_dir: Output directory for results

    Returns:
        RunResult with status and timing
    """
    start_time = time.time()

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Copy input file to output directory if not already there
    input_basename = os.path.basename(input_file)
    dest = os.path.join(output_dir, input_basename)
    if os.path.abspath(input_file) != os.path.abspath(dest):
        shutil.copy(input_file, dest)

    input_stem = input_basename.replace('.inp', '')
    abs_output = os.path.abspath(output_dir)
    cycles = config.fluka.cycles

    # Mirror run_fluka.sh: work in /fluka_work, set FLUPRO/FLUFOR, copy results back
    inner_script = (
        "set -e; "
        "export FLUPRO=/usr/local/fluka; "
        "export FLUFOR=gfortran; "
        "mkdir -p /fluka_work && cd /fluka_work; "
        f"cp /data/{input_basename} .; "
        f"$FLUPRO/bin/rfluka -N0 -M{cycles} {input_stem}; "
        # Merge USRBIN (unit 21) if present
        f"if ls {input_stem}001_fort.21 2>/dev/null; then "
        f"  for i in $(seq -f '%03g' 1 {cycles}); do "
        f"    [ -f {input_stem}${{i}}_fort.21 ] && echo {input_stem}${{i}}_fort.21; "
        "  done > usrbin21.lst; "
        "  echo '' >> usrbin21.lst; echo 'edep_xz.bnn' >> usrbin21.lst; "
        "  $FLUPRO/bin/usbsuw < usrbin21.lst; "
        "  echo -e 'edep_xz.bnn\\nedep_xz.dat\\n' | $FLUPRO/bin/usbrea; "
        "fi; "
        # Merge USRBDX (unit 23) if present
        f"if ls {input_stem}001_fort.23 2>/dev/null; then "
        f"  for i in $(seq -f '%03g' 1 {cycles}); do "
        f"    [ -f {input_stem}${{i}}_fort.23 ] && echo {input_stem}${{i}}_fort.23; "
        "  done > usrbdx23.lst; "
        "  echo '' >> usrbdx23.lst; echo 'neut_exit.bnn' >> usrbdx23.lst; "
        "  $FLUPRO/bin/usxsuw < usrbdx23.lst; "
        "  echo -e 'neut_exit.bnn\\nneut_exit.dat\\n' | $FLUPRO/bin/usxrea; "
        "fi; "
        "cp -f *.bnn *.dat *.out *.log *.err /data/ 2>/dev/null || true"
    )

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{abs_output}:/data",
        FLUKA_IMAGE,
        "bash", "-c", inner_script,
    ]

    returncode, stdout, stderr = run_command(cmd)

    # Write run log regardless of outcome
    with open(os.path.join(output_dir, "run.log"), 'w') as f:
        f.write(f"=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}\n")

    runtime = time.time() - start_time

    return RunResult(
        code='fluka',
        model=neutron_library,
        success=(returncode == 0),
        output_dir=output_dir,
        runtime_seconds=runtime,
        error_message=stderr if returncode != 0 else None,
    )


def run_fluka_flugg(
    config: SimulationConfig,
    neutron_library: str,
    input_file: str,
    output_dir: str,
) -> RunResult:
    """
    Run FLUKA simulation with FLUGG (external GDML geometry).

    Args:
        config: Simulation configuration
        neutron_library: Neutron library name
        input_file: Path to FLUKA input file
        output_dir: Output directory for results

    Returns:
        RunResult with status and timing
    """
    start_time = time.time()

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Copy input file to output directory if not already there
    input_basename = os.path.basename(input_file)
    dest = os.path.join(output_dir, input_basename)
    if os.path.abspath(input_file) != os.path.abspath(dest):
        shutil.copy(input_file, dest)

    # Get absolute path to GDML file
    gdml_path = os.path.abspath(config.geometry_gdml)

    # Docker command for FLUGG
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{os.path.abspath(output_dir)}:/data",
        "-v", f"{gdml_path}:/geometry.gdml:ro",
        "-e", "FLUGG_GDML=/geometry.gdml",
        "-w", "/data",
        FLUGG_IMAGE,
        "flugg_run.sh", input_basename, str(config.fluka.cycles),
    ]

    returncode, stdout, stderr = run_command(cmd)

    # Process output files
    if returncode == 0:
        merge_cmd = [
            "docker", "run", "--rm",
            "-v", f"{os.path.abspath(output_dir)}:/data",
            "-w", "/data",
            FLUGG_IMAGE,
            "bash", "-c",
            "for f in *_fort.21; do "
            "$FLUPRO/bin/usbsuw <<< \"${f%_fort.21}\" && "
            "$FLUPRO/bin/usbrea <<< \"${f%.21}.bnn\"; done 2>/dev/null || true"
        ]
        run_command(merge_cmd)

    runtime = time.time() - start_time

    return RunResult(
        code='fluka',
        model=neutron_library,
        success=(returncode == 0),
        output_dir=output_dir,
        runtime_seconds=runtime,
        error_message=stderr if returncode != 0 else None,
    )


def run_geant4(
    config: SimulationConfig,
    physics_list: str,
    macro_file: str,
    output_dir: str,
) -> RunResult:
    """
    Run Geant4 simulation in Docker.

    Args:
        config: Simulation configuration
        physics_list: Physics list name
        macro_file: Path to Geant4 macro file
        output_dir: Output directory for results

    Returns:
        RunResult with status and timing
    """
    start_time = time.time()

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Copy macro file to output directory if not already there
    macro_basename = os.path.basename(macro_file)
    dest = os.path.join(output_dir, macro_basename)
    if os.path.abspath(macro_file) != os.path.abspath(dest):
        shutil.copy(macro_file, dest)

    # Get absolute path to GDML file
    gdml_path = os.path.abspath(config.geometry_gdml)

    # Docker command for Geant4
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{os.path.abspath(output_dir)}:/data",
        "-v", f"{gdml_path}:/geometry.gdml:ro",
        "-w", "/data",
        GEANT4_IMAGE,
        "comparison_app",
        "-g", "/geometry.gdml",
        "-p", physics_list,
        "-m", macro_basename,
        "-o", "/data",
    ]

    returncode, stdout, stderr = run_command(cmd)

    runtime = time.time() - start_time

    # Write log
    with open(os.path.join(output_dir, "run.log"), 'w') as f:
        f.write(f"=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}\n")

    return RunResult(
        code='geant4',
        model=physics_list,
        success=(returncode == 0),
        output_dir=output_dir,
        runtime_seconds=runtime,
        error_message=stderr if returncode != 0 else None,
    )


class ComparisonRunner:
    """
    Orchestrates running multiple FLUKA and Geant4 simulations.
    """

    def __init__(self, config: SimulationConfig, use_flugg: bool = False):
        """
        Initialize the runner.

        Args:
            config: Simulation configuration
            use_flugg: Whether to use FLUGG for FLUKA runs
        """
        self.config = config
        self.use_flugg = use_flugg
        self.results: List[RunResult] = []

    def run_all(
        self,
        fluka_models: Optional[List[str]] = None,
        geant4_models: Optional[List[str]] = None,
        parallel: bool = False,
        max_workers: int = 4,
    ) -> List[RunResult]:
        """
        Run all configured simulations.

        Args:
            fluka_models: List of FLUKA models to run (None = all from config)
            geant4_models: List of Geant4 models to run (None = all from config)
            parallel: Whether to run simulations in parallel
            max_workers: Maximum parallel workers

        Returns:
            List of RunResult objects
        """
        from .fluka_generator import generate_fluka_input, generate_fluka_input_native
        from .geant4_generator import generate_geant4_macro

        # Determine models to run
        if fluka_models is None:
            fluka_models = self.config.fluka.neutron_libraries if self.config.fluka.enabled else []
        if geant4_models is None:
            geant4_models = self.config.geant4.physics_lists if self.config.geant4.enabled else []

        base_output = self.config.output_dir
        tasks = []

        # Prepare FLUKA tasks
        for lib in fluka_models:
            output_dir = os.path.join(base_output, 'fluka', lib)
            input_file = os.path.join(output_dir, 'input.inp')

            if self.use_flugg:
                generate_fluka_input(self.config, lib, input_file)
                tasks.append(('fluka_flugg', lib, input_file, output_dir))
            else:
                generate_fluka_input_native(self.config, lib, input_file)
                tasks.append(('fluka_native', lib, input_file, output_dir))

        # Prepare Geant4 tasks
        for phys in geant4_models:
            output_dir = os.path.join(base_output, 'geant4', phys)
            macro_file = os.path.join(output_dir, 'run.mac')
            generate_geant4_macro(self.config, phys, macro_file)
            tasks.append(('geant4', phys, macro_file, output_dir))

        # Execute tasks
        if parallel and len(tasks) > 1:
            self.results = self._run_parallel(tasks, max_workers)
        else:
            self.results = self._run_sequential(tasks)

        return self.results

    def _run_sequential(self, tasks: List[tuple]) -> List[RunResult]:
        """Run tasks sequentially."""
        results = []
        for task_type, model, input_file, output_dir in tasks:
            print(f"Running {task_type}/{model}...")
            if task_type == 'fluka_native':
                result = run_fluka_native(
                    self.config, model, input_file, output_dir
                )
            elif task_type == 'fluka_flugg':
                result = run_fluka_flugg(
                    self.config, model, input_file, output_dir
                )
            else:  # geant4
                result = run_geant4(
                    self.config, model, input_file, output_dir
                )
            results.append(result)
            status = "OK" if result.success else "FAILED"
            print(f"  {status} ({result.runtime_seconds:.1f}s)")
            if not result.success:
                log = os.path.join(result.output_dir, "run.log")
                if os.path.exists(log):
                    print(f"  Log: {log}")
                if result.error_message:
                    print(f"  Error: {result.error_message[:200]}")
        return results

    def _run_parallel(self, tasks: List[tuple], max_workers: int) -> List[RunResult]:
        """Run tasks in parallel."""
        results = []

        def run_task(task):
            task_type, model, input_file, output_dir = task
            if task_type == 'fluka_native':
                return run_fluka_native(
                    self.config, model, input_file, output_dir
                )
            elif task_type == 'fluka_flugg':
                return run_fluka_flugg(
                    self.config, model, input_file, output_dir
                )
            else:
                return run_geant4(
                    self.config, model, input_file, output_dir
                )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(run_task, task): task for task in tasks
            }

            for future in as_completed(future_to_task):
                task = future_to_task[future]
                task_type, model, _, _ = task
                try:
                    result = future.result()
                    results.append(result)
                    status = "OK" if result.success else "FAILED"
                    print(f"{task_type}/{model}: {status} ({result.runtime_seconds:.1f}s)")
                except Exception as e:
                    print(f"{task_type}/{model}: ERROR - {e}")
                    results.append(RunResult(
                        code=task_type.split('_')[0],
                        model=model,
                        success=False,
                        output_dir=task[3],
                        runtime_seconds=0,
                        error_message=str(e),
                    ))

        return results

    def generate_summary(self, output_file: Optional[str] = None) -> str:
        """Generate a summary of all runs."""
        lines = ["code,model,success,runtime_s,error"]
        for r in self.results:
            error = r.error_message.replace(',', ';')[:100] if r.error_message else ""
            lines.append(f"{r.code},{r.model},{r.success},{r.runtime_seconds:.1f},{error}")

        summary = "\n".join(lines)

        if output_file:
            with open(output_file, 'w') as f:
                f.write(summary)

        return summary
