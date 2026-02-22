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

from .config_parser import SimulationConfig, FLUKA_NEUTRON_LIBS


# Docker image names
FLUGG_IMAGE = "flugg:latest"
GEANT4_IMAGE = "comparison_app:latest"  # built from docker/Dockerfile.comparison
FLUKA_IMAGE = "fluka:ggi"

# Default FLUKA template (relative to working directory when run_comparison.py is invoked)
DEFAULT_FLUKA_TEMPLATE = "neutron_bpe.inp"


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
    template_path: str,
    output_dir: str,
) -> RunResult:
    """
    Run FLUKA simulation with native geometry in Docker.

    Mirrors run_fluka.sh exactly: mounts the project directory to /data,
    copies neutron_bpe.inp from /data, patches with sed inside the
    container, then runs rfluka.

    Args:
        config: Simulation configuration
        neutron_library: Neutron library name (JEFF, ENDF, etc.)
        template_path: Path to the FLUKA template .inp file (neutron_bpe.inp)
        output_dir: Output directory for results

    Returns:
        RunResult with status and timing
    """
    start_time = time.time()

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    abs_output = os.path.abspath(output_dir)
    abs_template = os.path.abspath(template_path)
    template_dir = os.path.dirname(abs_template)
    template_basename = os.path.basename(abs_template)   # e.g. neutron_bpe.inp
    input_stem = template_basename.replace('.inp', '')    # e.g. neutron_bpe

    lib_sdum = FLUKA_NEUTRON_LIBS.get(neutron_library, neutron_library[:8])
    cycles = config.fluka.cycles
    energy_gev = config.particle.energy_gev

    # Compute output subdirectory path relative to project root
    # We mount the project directory (template_dir) to /data, matching run_fluka.sh
    rel_output = os.path.relpath(abs_output, template_dir)

    # Mirror run_fluka.sh exactly:
    #  - Mount project directory to /data (single volume, like run_fluka.sh)
    #  - Copy input from /data to /fluka_work
    #  - Use set -e for strict error handling (like run_fluka.sh)
    #  - Patch with sed using same printf formats
    #  - Run rfluka with error handling
    #  - Copy outputs to /data/$OUTPUT_DIR
    inner_script = "\n".join([
        "set -e",
        # Install gfortran + wget exactly like run_fluka.sh
        "if ! command -v gfortran &> /dev/null || ! command -v wget &> /dev/null; then",
        "  echo 'Installing required packages...'",
        "  apt-get update -qq && apt-get install -y -qq gfortran wget",
        "fi",
        # Variable setup matching run_fluka.sh style
        "FLUPRO=/usr/local/fluka",
        "export FLUPRO",
        "export FLUFOR=gfortran",
        f'INPUT_FILE="{template_basename}"',
        'INPUT_BASE="${INPUT_FILE%.inp}"',
        f'CYCLES={cycles}',
        f'ENERGY_GEV={energy_gev}',
        f'PWXS_SDUM="{lib_sdum}"',
        f'OUTPUT_DIR="{rel_output}"',
        "mkdir -p /fluka_work",
        "cd /fluka_work",
        # Copy template from /data (same as run_fluka.sh)
        "cp /data/$INPUT_FILE .",
        # Patch BEAM: compute energy string with bash printf, same as run_fluka.sh
        'ENERGY_STR=$(printf "%10.4E" $ENERGY_GEV)',
        'sed -i "s/^BEAM .*/BEAM      $ENERGY_STR       0.0       0.0       0.0       0.0       1.0NEUTRON/" $INPUT_FILE',
        'echo "Set neutron energy to $ENERGY_GEV GeV"',
        # Remove any existing LOW-PWXS then re-insert before RANDOMIZ
        'sed -i "/^LOW-PWXS/d" $INPUT_FILE',
        'PWXS_CARD=$(printf "%-10s%10.1f%10.1f%10.1f%10.1f%10.1f%10.1f%-8s" "LOW-PWXS" 1.0 0.0 0.0 0.0 0.0 0.0 "$PWXS_SDUM")',
        'sed -i "/^RANDOMIZ/i $PWXS_CARD" $INPUT_FILE',
        'echo "Added LOW-PWXS card for library: $PWXS_SDUM"',
        'echo "FLUKA path: $FLUPRO"',
        'echo "Running simulation with rfluka..."',
        # Run rfluka with error handling (same pattern as run_fluka.sh)
        f"$FLUPRO/bin/rfluka -N0 -M${{CYCLES}} ${{INPUT_BASE}} || {{",
        '  echo ""',
        '  echo "=== FLUKA run failed. Checking logs ==="',
        '  echo "--- .out file ---"',
        '  cat ${INPUT_BASE}001.out 2>/dev/null | tail -100 || echo "No .out file"',
        '  echo "--- .err file ---"',
        '  cat ${INPUT_BASE}001.err 2>/dev/null || echo "No .err file"',
        '  echo "--- .log file ---"',
        '  cat ${INPUT_BASE}001.log 2>/dev/null || echo "No .log file"',
        "  mkdir -p /data/$OUTPUT_DIR",
        "  cp -f *.out /data/$OUTPUT_DIR/ 2>/dev/null || true",
        "  cp -f *.err /data/$OUTPUT_DIR/ 2>/dev/null || true",
        "  cp -f *.log /data/$OUTPUT_DIR/ 2>/dev/null || true",
        "  exit 1",
        "}",
        'echo ""',
        'echo "Simulation complete. Processing output..."',
        # Merge USRBIN (unit 21)
        f"if ls {input_stem}001_fort.21 1>/dev/null 2>&1; then",
        '  echo "Merging USRBIN output files..."',
        f"  echo '{input_stem}001_fort.21' > usrbin21.lst",
        f"  for i in $(seq -f '%03g' 2 $CYCLES); do",
        f"    [ -f '{input_stem}'${{i}}_fort.21 ] && echo '{input_stem}'${{i}}_fort.21 >> usrbin21.lst",
        "  done",
        "  echo '' >> usrbin21.lst",
        "  echo 'usrbin21.lst_sum' >> usrbin21.lst",
        "  $FLUPRO/bin/usbsuw < usrbin21.lst",
        "  [ -f usrbin21.lst_sum ] && mv usrbin21.lst_sum edep_xz.bnn",
        "fi",
        # Merge USRBDX (unit 23)
        f"if ls {input_stem}001_fort.23 1>/dev/null 2>&1; then",
        '  echo "Processing USRBDX output (unit 23)..."',
        f"  echo '{input_stem}001_fort.23' > usrbdx23.lst",
        f"  for i in $(seq -f '%03g' 2 $CYCLES); do",
        f"    [ -f '{input_stem}'${{i}}_fort.23 ] && echo '{input_stem}'${{i}}_fort.23 >> usrbdx23.lst",
        "  done",
        "  echo '' >> usrbdx23.lst",
        "  echo 'neut_exit.bnn' >> usrbdx23.lst",
        "  $FLUPRO/bin/usxsuw < usrbdx23.lst",
        "fi",
        # Convert to ASCII
        'echo "Converting to ASCII format..."',
        "if [ -f edep_xz.bnn ]; then",
        "  echo -e 'edep_xz.bnn\\nedep_xz.dat\\n' | $FLUPRO/bin/usbrea",
        "fi",
        "if [ -f neut_exit.bnn ]; then",
        "  echo -e 'neut_exit.bnn\\nneut_exit.dat\\n' | $FLUPRO/bin/usxrea",
        "fi",
        # Copy outputs to host
        "mkdir -p /data/$OUTPUT_DIR",
        "cp -f *.bnn /data/$OUTPUT_DIR/ 2>/dev/null || true",
        "cp -f *.dat /data/$OUTPUT_DIR/ 2>/dev/null || true",
        "cp -f *.out /data/$OUTPUT_DIR/ 2>/dev/null || true",
        "cp -f *.log /data/$OUTPUT_DIR/ 2>/dev/null || true",
        "cp -f *.err /data/$OUTPUT_DIR/ 2>/dev/null || true",
        'echo ""',
        'echo "Output files copied to /data/$OUTPUT_DIR/"',
        "ls -la /data/$OUTPUT_DIR/",
    ])

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{template_dir}:/data",
        "-w", "/fluka_work",
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

    def __init__(self, config: SimulationConfig, use_flugg: bool = False,
                 template_path: str = DEFAULT_FLUKA_TEMPLATE):
        """
        Initialize the runner.

        Args:
            config: Simulation configuration
            use_flugg: Whether to use FLUGG for FLUKA runs
            template_path: Path to the FLUKA template .inp file
        """
        self.config = config
        self.use_flugg = use_flugg
        self.template_path = template_path
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
        from .geant4_generator import generate_geant4_macro

        # Determine models to run
        if fluka_models is None:
            fluka_models = self.config.fluka.neutron_libraries if self.config.fluka.enabled else []
        if geant4_models is None:
            geant4_models = self.config.geant4.physics_lists if self.config.geant4.enabled else []

        base_output = self.config.output_dir
        tasks = []

        # Prepare FLUKA tasks
        # For native mode: pass template_path; sed patching done inside container.
        # For FLUGG mode: pre-generate patched input file.
        for lib in fluka_models:
            output_dir = os.path.join(base_output, 'fluka', lib)
            os.makedirs(output_dir, exist_ok=True)

            if self.use_flugg:
                from .fluka_generator import generate_fluka_input
                input_file = os.path.join(output_dir, 'input.inp')
                generate_fluka_input(self.config, lib, input_file, self.template_path)
                tasks.append(('fluka_flugg', lib, input_file, output_dir))
            else:
                # Pass template_path as third element; no pre-generation needed
                tasks.append(('fluka_native', lib, self.template_path, output_dir))

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
        for task_type, model, input_or_template, output_dir in tasks:
            print(f"Running {task_type}/{model}...")
            if task_type == 'fluka_native':
                result = run_fluka_native(
                    self.config, model, input_or_template, output_dir
                )
            elif task_type == 'fluka_flugg':
                result = run_fluka_flugg(
                    self.config, model, input_or_template, output_dir
                )
            else:  # geant4
                result = run_geant4(
                    self.config, model, input_or_template, output_dir
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
            task_type, model, input_or_template, output_dir = task
            if task_type == 'fluka_native':
                return run_fluka_native(
                    self.config, model, input_or_template, output_dir
                )
            elif task_type == 'fluka_flugg':
                return run_fluka_flugg(
                    self.config, model, input_or_template, output_dir
                )
            else:
                return run_geant4(
                    self.config, model, input_or_template, output_dir
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
