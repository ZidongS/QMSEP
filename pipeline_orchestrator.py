#!/usr/bin/env python3
"""Run the QMSEP dielectric-charge pipeline from CLI inputs and JSON config."""

import os
import sys
import time
import json
import re
import argparse
import concurrent.futures
from datetime import datetime
from typing import List, Dict
import shutil

# Add the current directory to Python path for importing modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.logger import PipelineLogger
from utils.timing import Timer
from utils.file_manager import FileManager
from utils.report_generator import ReportGenerator
from steps.data_preprocessing import DataPreprocessor
from steps.orca_runner import OrcaRunner
from steps.charge_extractor import ChargeExtractor
from steps.point_sampler import PointSampler
from steps.potential_calculator import PotentialCalculator

LOCAL_CLI_CONFIG = os.path.expanduser("~/.qmsep_cli_config.json")
os.environ["OMP_STACKSIZE"] = "200M"


class PipelineOrchestrator:
    """Main orchestrator for the dielectric charge calculation pipeline"""

    def __init__(self, config: Dict):
        self.config = config
        self._auto_setup_environment()
        self.logger = PipelineLogger(config.get("log_level", "INFO"))
        self.timer = Timer()
        self.file_manager = FileManager(config)
        self.report_generator = ReportGenerator(config)

        # Initialize step processors
        self.data_preprocessor = DataPreprocessor(config, self.logger)
        self.orca_runner = OrcaRunner(config, self.logger)
        self.charge_extractor = ChargeExtractor(config, self.logger)
        self.point_sampler = PointSampler(config, self.logger)
        self.potential_calculator = PotentialCalculator(config, self.logger)

        self.results = {}

    def _auto_setup_environment(self):
        orca_bin = self.config.get("orca_bin_path", "orca")
        real_orca_path = shutil.which(orca_bin)
        if real_orca_path:
            orca_dir = os.path.dirname(os.path.abspath(real_orca_path))
            conda_lib = os.path.join(os.environ.get("CONDA_PREFIX", ""), "lib")
            extra_libs = []
            if os.path.exists(conda_lib):
                extra_libs.append(conda_lib)

            if os.path.exists(orca_dir):
                extra_libs.append(os.path.join(orca_dir, "lib"))

            old_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = (
                ":".join(extra_libs) + (":" if old_ld_path else "") + old_ld_path
            )
            old_path = os.environ.get("PATH", "")
            if orca_dir not in old_path:
                os.environ["PATH"] = f"{orca_dir}:{old_path}"

    def run_single_pdb(self, pdb_id: str) -> Dict:
        """Run the complete pipeline for a single PDB ID"""
        pdb_output_dir = self.file_manager.get_pdb_output_dir(pdb_id)
        self.logger.set_pdb_log_file(str(pdb_output_dir / "pipeline.log"))
        print("\n" + "=" * 74)
        print(f"NOW PROCESSING PDB ID: {pdb_id}")
        print("Start cooking SEP for you!")
        print("=" * 74)
        self.logger.info(f"Starting pipeline for PDB ID: {pdb_id}")
        
        temp_dir = None
        result = {
            'pdb_id': pdb_id,
            'status': 'failed',
            'start_time': datetime.now(),
            'end_time': None,
            'step_times': {},
            'error': None,
            'atom_count': 0,
            'total_charge': 0,
            'potential_stats': {}
        }
        
        try:
            temp_dir = self.file_manager.create_temp_directory(pdb_id)
            self.logger.info(f"Created temporary directory: {temp_dir}")
            
            files_to_save = []

            # Step 1: Data preprocessing.
            self.logger.info(f"Step 1/5 - Data preprocessing for {pdb_id}")
            step_timer = Timer()
            pqr_file, atom_count, total_charge = self.data_preprocessor.process(pdb_id, temp_dir)
            files_to_save.append(pqr_file)
            result['atom_count'] = atom_count
            result['total_charge'] = total_charge
            result['step_times']['data_preprocessing'] = step_timer.elapsed()
            self.logger.success(f"Step 1 completed in {result['step_times']['data_preprocessing']:.2f}s")
            
            # Step 2: ORCA calculations.
            self.logger.info(f"Step 2/5 - Running ORCA calculations for {pdb_id}")
            step_timer = Timer()
            orca_results = self.orca_runner.run(pdb_id, temp_dir)
            files_to_save.extend([path for path in orca_results.values() if path])
            result['step_times']['orca_calculations'] = step_timer.elapsed()
            self.logger.success(f"Step 2 completed in {result['step_times']['orca_calculations']:.2f}s")
            
            # Step 3: Charge extraction.
            self.logger.info(f"Step 3/5 - Extracting reacting charges for {pdb_id}")
            step_timer = Timer()
            charge_file = self.charge_extractor.extract(pdb_id, temp_dir)
            result['step_times']['charge_extraction'] = step_timer.elapsed()
            self.logger.success(f"Step 3 completed in {result['step_times']['charge_extraction']:.2f}s")
            
            # Step 4: Surface point sampling.
            self.logger.info(f"Step 4/5 - Sampling surface points for {pdb_id}")
            step_timer = Timer()
            surface_files = self.point_sampler.sample(pdb_id, temp_dir)
            result['step_times']['point_sampling'] = step_timer.elapsed()
            self.logger.success(f"Step 4 completed in {result['step_times']['point_sampling']:.2f}s")
            
            # Step 5: Potential calculation.
            self.logger.info(f"Step 5/5 - Calculating potentials for {pdb_id}")
            step_timer = Timer()
            checkpoint_file = self.potential_calculator.calculate(pdb_id, temp_dir)
            files_to_save.append(checkpoint_file)
            result['step_times']['potential_calculation'] = step_timer.elapsed()
            
            potential_stats = self._extract_potential_stats(checkpoint_file)
            result['potential_stats'] = potential_stats
            self.logger.success(f"Step 5 completed in {result['step_times']['potential_calculation']:.2f}s")
            
            # Save designated output files.
            self.file_manager.save_output_files(pdb_id, files_to_save)
            self.logger.info(f"Saved output files to directory: {os.path.join(self.config['output_dir'], pdb_id)}")
            self._write_run_context_file(pdb_id, result)

            result['status'] = 'success'
            result['end_time'] = datetime.now()
            
            if not self.config.get('keep_intermediates', False):
                self.file_manager.cleanup_temp_directory(temp_dir)
                self.logger.info(f"Cleaned up temporary files for {pdb_id}")
            
            self.logger.success(f"Pipeline completed successfully for {pdb_id}")
            
        except Exception as e:
            result['error'] = str(e)
            result['end_time'] = datetime.now()
            self.logger.error(f"Pipeline failed for {pdb_id}: {str(e)}")
            
            if temp_dir and not self.config.get('keep_intermediates', False):
                self.file_manager.cleanup_temp_directory(temp_dir)
        finally:
            self.logger.clear_pdb_log_file()
        
        return result
    
    def run_multiple_pdbs(self, pdb_ids: List[str], parallel: bool = False, max_workers: int = 1) -> List[Dict]:
        """Run pipeline for multiple PDB IDs, optionally in parallel"""
        self.logger.info(f"Starting pipeline for {len(pdb_ids)} PDB IDs")
        
        if parallel and max_workers > 1:
            self.logger.info(f"Running in parallel mode with {max_workers} workers")
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self.run_single_pdb, pdb_id) for pdb_id in pdb_ids]
                results = []
                for future in concurrent.futures.as_completed(futures):
                    results.append(future.result())
        else:
            self.logger.info("Running in sequential mode")
            results = []
            for pdb_id in pdb_ids:
                result = self.run_single_pdb(pdb_id)
                results.append(result)
        
        return results
    
    def _extract_potential_stats(self, checkpoint_file: str) -> Dict:
        """Extract potential statistics from checkpoint file"""
        potentials = []
        try:
            with open(checkpoint_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        try:
                            potential = float(parts[3])
                            potentials.append(potential)
                        except ValueError:
                            continue
            
            if potentials:
                return {
                    'min': min(potentials),
                    'max': max(potentials),
                    'mean': sum(potentials) / len(potentials),
                    'count': len(potentials)
                }
            else:
                return {'min': 0, 'max': 0, 'mean': 0, 'count': 0}
                
        except Exception as e:
            self.logger.warning(f"Could not extract potential stats: {e}")
            return {'min': 0, 'max': 0, 'mean': 0, 'count': 0}

    def _write_run_context_file(self, pdb_id: str, result: Dict):
        """Write run metadata and step details into the PDB output folder."""
        output_dir = self.file_manager.get_pdb_output_dir(pdb_id)
        context_file = output_dir / "run_context.txt"
        step_descriptions = self.report_generator.step_descriptions

        with open(context_file, "w", encoding="utf-8") as f:
            f.write("QMSEP RUN CONTEXT\n")
            f.write("=" * 60 + "\n")
            f.write(f"PDB ID: {pdb_id}\n")
            f.write(f"Status: {result.get('status')}\n")
            f.write(f"Task start time: {self.config.get('task_start_time')}\n")
            f.write(f"PDB run start: {result.get('start_time')}\n")
            f.write(f"PDB run end: {result.get('end_time')}\n\n")

            f.write("Runtime parameters and brief descriptions:\n")
            for key, description in self.config.get("parameter_descriptions", {}).items():
                f.write(f"- {key}: {self.config.get(key)}\n")
                f.write(f"  {description}\n")

            f.write("\nStep times and step descriptions:\n")
            for step, elapsed in result.get("step_times", {}).items():
                f.write(f"- {step}: {elapsed:.2f}s\n")
                f.write(f"  {step_descriptions.get(step, 'No description available.')}\n")


def build_default_config() -> Dict:
    """Return the baseline pipeline configuration."""
    return {
        "output_dir": "output",
        "temp_dir": "temp",
        "keep_intermediates": False,
        "surface_mode": "ses",
        "sample_points": 10000,
        "grid_spacing": 0.1,
        "log_level": "INFO",
        "multiwfn_path": os.environ.get("QMSEP_MULTIWFN_PATH", "Multiwfn_noGUI"),
        "orca_bin_path": os.environ.get("QMSEP_ORCA_BIN_PATH", "orca"),
        "max_retries": 1,
        "retry_delay": 5,
        "pdb2pqr_force_field": "SWANSON",
        "pqr_radius_scale": 1.2,
        "orca_functional": "B3LYP",
        "orca_basis_set": "6-31G*",
        "orca_nprocs": 32,
        "orca_maxcore": 7000,
        "eps_gaussian_exponent": 5.0,
        "eps_target_iso_level": 0.999,
    }


def get_parameter_descriptions() -> Dict[str, str]:
    """Return short descriptions for runtime configuration keys."""
    return {
        "surface_mode": "Surface sampling algorithm. Choose from vdw/ses/eps.",
        "sample_points": "Number of final sampling points exported for potential calculation.",
        "grid_spacing": "Grid spacing in angstrom used to build volumetric fields.",
        "pdb2pqr_force_field": "Force field for pdb2pqr. Options: AMBER/CHARMM/PARSE/TYL06/PEOEPB/SWANSON.",
        "pqr_radius_scale": "Scale factor applied to atomic radii in ORCA CPCM cavity.",
        "orca_functional": "DFT functional keyword used in both gas and solvated ORCA inputs.",
        "orca_basis_set": "Basis set keyword used in ORCA inputs.",
        "orca_nprocs": "Number of CPU cores requested by ORCA %pal section.",
        "orca_maxcore": "Maximum memory per core (MB) requested by ORCA %maxcore.",
        "eps_gaussian_exponent": "Gaussian exponent for EPS density model (effective in eps mode).",
        "eps_target_iso_level": "Target rho_mol isosurface value for EPS surface extraction (eps mode).",
        "multiwfn_path": "Executable path for Multiwfn.",
        "orca_bin_path": "Native ORCA executable path.",
    }


def print_qmsep_banner():
    class C:
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        MAGENTA = '\033[95m'
        BOLD = '\033[1m'
        RESET = '\033[0m'

    logo = [
        fr"{C.GREEN}      . : .         {C.CYAN}____   __  __  _____  ______  _____  {C.RESET}",
        fr"{C.GREEN}    '       '      {C.CYAN}/ __ \ |  \/  |/ ____||  ____||  __ \ {C.RESET}",
        fr"{C.GREEN}  .   {C.BLUE}\ | /{C.GREEN}   .   {C.CYAN}| |  | || \  / | (___  | |__   | |__) |{C.RESET}",
        fr"{C.GREEN} -   {C.BLUE}-- {C.MAGENTA}{C.BOLD}Ψ{C.RESET}{C.BLUE} --{C.GREEN}   -  {C.CYAN}| |  | || |\/| |\___ \ |  __|  |  ___/ {C.RESET}",
        fr"{C.GREEN}  .   {C.BLUE}/ | \{C.GREEN}   .   {C.CYAN}| |__| || |  | |____) || |____ | |     {C.RESET}",
        fr"{C.GREEN}    .       .      {C.CYAN}\___\_\|_|  |_|_____/ |______||_|     {C.RESET}",
        fr"{C.GREEN}      ' : '                                              {C.RESET}"
    ]

    info = [
        "QMSEP - Quantum Mechanics Surface Electrostatic Potential",
        "-",
        "Author: Zidong Shu | Version: v1.0.0 | Year: 2026 | License: MIT",
        "-",
        "Acknowledgements:",
        "[*] ORCA: Neese, F. (2012). WIREs Comput Mol Sci, 2(1), 73-78.",
        "    DOI: 10.1002/wcms.81",
        "[*] Multiwfn: Lu & Chen (2012), J. Comput. Chem. 33, 580-592.",
        "    DOI: 10.1002/jcc.22885",
        "[*] Multiwfn: Lu (2024), J. Chem. Phys. 161, 082503.",
        "    DOI: 10.1063/5.0216272"
    ]

    width = 76
    
    print(f"{C.BLUE}╔{'═' * width}╗{C.RESET}")
    print(f"{C.BLUE}║{' ' * width}║{C.RESET}")
    
    pad_l = " " * 9
    pad_r = " " * 10
    
    for line in logo:
        print(f"{C.BLUE}║{C.RESET}{pad_l}{line}{pad_r}{C.BLUE}║{C.RESET}")
        
    print(f"{C.BLUE}║{' ' * width}║{C.RESET}")
    
    for line in info:
        if line == "-":
            print(f"{C.BLUE}╠{'═' * width}╣{C.RESET}")
        elif line.startswith("QMSEP"):
            padded_line = line.center(width)
            print(f"{C.BLUE}║{C.YELLOW}{C.BOLD}{padded_line}{C.RESET}{C.BLUE}║{C.RESET}")
        elif line.startswith("Author"):
            padded_line = line.center(width)
            print(f"{C.BLUE}║{C.YELLOW}{padded_line}{C.BLUE}║{C.RESET}")
        elif line.startswith("Acknowledgements"):
            padded_line = f"  {line}".ljust(width)
            print(f"{C.BLUE}║{C.GREEN}{padded_line}{C.BLUE}║{C.RESET}")
        else:
            padded_line = f"  {line}".ljust(width)
            print(f"{C.BLUE}║{C.RESET}{padded_line}{C.BLUE}║{C.RESET}")
            
    print(f"{C.BLUE}╚{'═' * width}╝{C.RESET}")
    print()


def load_json_or_jsonc(config_path: str) -> Dict:
    """Load JSON/JSONC configuration files with inline comments support."""
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    without_block = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    without_line = re.sub(r"^\s*//.*$", "", without_block, flags=re.MULTILINE)
    return json.loads(without_line)


def save_cli_registration(updates: Dict):
    """Persist quick CLI registration values in per-user config file."""
    existing = {}
    if os.path.exists(LOCAL_CLI_CONFIG):
        with open(LOCAL_CLI_CONFIG, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing.update(updates)
    with open(LOCAL_CLI_CONFIG, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    print(f"Saved quick registration into: {LOCAL_CLI_CONFIG}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="QMSEP dielectric charge calculation pipeline")
    parser.add_argument("pdb_ids", nargs="*", help="PDB ID(s) to process")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel processing")
    parser.add_argument("--max-workers", type=int, default=1, help="Maximum number of parallel workers")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    parser.add_argument("--temp-dir", type=str, default=None, help="Temporary directory")
    parser.add_argument("--keep-intermediates", action="store_true", help="Keep intermediate files")
    parser.add_argument("--surface-mode", choices=["vdw", "ses", "eps"], default=None, help="Surface sampling mode")
    parser.add_argument("--sample-points", type=int, default=None, help="Number of surface sampling points")
    parser.add_argument("--grid-spacing", type=float, default=None, help="Grid spacing in angstrom")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None, help="Logging level")
    parser.add_argument("--multiwfn-path", type=str, default=None, help="Path to Multiwfn executable")
    parser.add_argument("--orca-bin-path", type=str, default=None, help="Path to ORCA executable")
    parser.add_argument("--pdb2pqr-force-field", choices=["AMBER", "CHARMM", "PARSE", "TYL06", "PEOEPB", "SWANSON"], default=None, help="Force field for pdb2pqr")
    parser.add_argument("--pqr-radius-scale", type=float, default=None, help="Radius scale factor for ORCA CPCM cavity")
    parser.add_argument("--orca-functional", type=str, default=None, help="ORCA functional keyword")
    parser.add_argument("--orca-basis-set", type=str, default=None, help="ORCA basis set keyword")
    parser.add_argument("--orca-nprocs", type=int, default=None, help="ORCA CPU cores")
    parser.add_argument("--orca-maxcore", type=int, default=None, help="ORCA maxcore (MB per core)")
    parser.add_argument("--eps-gaussian-exponent", type=float, default=None, help="EPS gaussian exponent (effective in eps mode)")
    parser.add_argument("--eps-target-iso-level", type=float, default=None, help="EPS target iso level (effective in eps mode)")
    parser.add_argument("--config", type=str, help="Configuration file path")
    parser.add_argument("--register-multiwfn-path", type=str, default=None, help="Save default Multiwfn path for future runs")
    parser.add_argument("--register-orca-bin-path", type=str, default=None, help="Save default ORCA binary path for future runs")
    
    args = parser.parse_args()
    registration_updates = {}
    if args.register_multiwfn_path:
        registration_updates["multiwfn_path"] = args.register_multiwfn_path
    if args.register_orca_bin_path:
        registration_updates["orca_bin_path"] = args.register_orca_bin_path
    if registration_updates:
        save_cli_registration(registration_updates)
        if not args.pdb_ids:
            return

    print_qmsep_banner()
    config = build_default_config()
    default_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(default_config_path):
        config.update(load_json_or_jsonc(default_config_path))
    if os.path.exists(LOCAL_CLI_CONFIG):
        config.update(load_json_or_jsonc(LOCAL_CLI_CONFIG))

    if args.config and os.path.exists(args.config):
        config.update(load_json_or_jsonc(args.config))

    cli_overrides = {
        "output_dir": args.output_dir,
        "temp_dir": args.temp_dir,
        "surface_mode": args.surface_mode,
        "sample_points": args.sample_points,
        "grid_spacing": args.grid_spacing,
        "log_level": args.log_level,
        "multiwfn_path": args.multiwfn_path,
        "orca_bin_path": args.orca_bin_path,
        "pdb2pqr_force_field": args.pdb2pqr_force_field,
        "pqr_radius_scale": args.pqr_radius_scale,
        "orca_functional": args.orca_functional,
        "orca_basis_set": args.orca_basis_set,
        "orca_nprocs": args.orca_nprocs,
        "orca_maxcore": args.orca_maxcore,
        "eps_gaussian_exponent": args.eps_gaussian_exponent,
        "eps_target_iso_level": args.eps_target_iso_level,
    }
    for key, value in cli_overrides.items():
        if value is not None:
            config[key] = value
    if args.keep_intermediates:
        config["keep_intermediates"] = True
    if not args.pdb_ids:
        parser.error("Please provide at least one PDB ID, or run only registration arguments.")
    config["task_start_time"] = datetime.now().isoformat(timespec="seconds")
    config["parameter_descriptions"] = get_parameter_descriptions()
    
    orchestrator = PipelineOrchestrator(config)
    
    main_timer = Timer()
    
    results = orchestrator.run_multiple_pdbs(args.pdb_ids, args.parallel, args.max_workers)
    
    total_time = main_timer.elapsed()
    report_file = orchestrator.report_generator.generate_report(results, total_time)
    
    successful = sum(1 for r in results if r['status'] == 'success')
    failed = len(results) - successful
    
    print(f"\n" + "="*60)
    print("PIPELINE SUMMARY")
    print(f"="*60)
    print(f"Total PDBs processed: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total time: {total_time:.2f} seconds")
    print(f"Detailed report: {report_file}")
    print(f"="*60)


if __name__ == "__main__":
    main()
