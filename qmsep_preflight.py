#!/usr/bin/env python3
"""Run professional preflight checks before executing QMSEP production jobs."""

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Dict, List, Tuple

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


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

def load_json_or_jsonc(path: str) -> Dict:
    """Load JSON or JSONC file by stripping comments before parsing."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    without_block = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    without_line = re.sub(r"^\s*//.*$", "", without_block, flags=re.MULTILINE)
    return json.loads(without_line)


def check_required_files() -> Tuple[bool, str]:
    """Check that core project files exist."""
    required_files = [
        "pipeline_orchestrator.py",
        "qmsep_preflight.py",
        "config.json",
        "README.md",
        "utils/logger.py",
        "steps/data_preprocessing.py",
        "steps/orca_runner.py",
        "steps/point_sampler.py",
        "steps/potential_calculator.py",
    ]
    missing = [path for path in required_files if not os.path.exists(path)]
    if missing:
        return False, f"Missing files: {missing}"
    return True, "Core project files are present."


def check_python_imports() -> Tuple[bool, str]:
    """Check imports required by pipeline modules."""
    try:
        __import__("numpy")
        __import__("scipy")
        __import__("skimage")
    except ImportError as exc:
        return False, f"Python dependency missing: {exc}"
    return True, "Python dependencies are importable."


def check_config_validity(config_path: str) -> Tuple[bool, str]:
    """Check config file can be parsed and has critical keys."""
    try:
        config = load_json_or_jsonc(config_path)
    except Exception as exc:
        return False, f"Config parsing failed: {exc}"

    required_keys = ["multiwfn_path", "surface_mode", "sample_points"]
    missing = [key for key in required_keys if key not in config]
    if missing:
        return False, f"Config missing required keys: {missing}"
    return True, "Config file structure is valid."


def check_orca_connection(config_path: str) -> Tuple[bool, str]:
    """Check ORCA binary connectivity."""
    config = load_json_or_jsonc(config_path)
    orca_bin_path = config.get("orca_bin_path", "orca")
    resolved_orca = shutil.which(orca_bin_path) if not os.path.isabs(orca_bin_path) else orca_bin_path
    if not resolved_orca or not os.path.exists(resolved_orca):
        return False, f"ORCA binary not found: {orca_bin_path}"
    if not os.access(resolved_orca, os.X_OK):
        return False, f"ORCA binary is not executable: {resolved_orca}"
    return True, f"ORCA binary is reachable: {resolved_orca}"


def check_multiwfn_connection(config_path: str) -> Tuple[bool, str]:
    """Check Multiwfn executable path and startup accessibility."""
    config = load_json_or_jsonc(config_path)
    multiwfn_path = config.get("multiwfn_path", "")
    if not os.path.exists(multiwfn_path):
        return False, f"Multiwfn executable not found: {multiwfn_path}"
    if not os.access(multiwfn_path, os.X_OK):
        return False, f"Multiwfn exists but is not executable: {multiwfn_path}"

    try:
        result = subprocess.run([multiwfn_path], input="q\n", capture_output=True, text=True, timeout=8)
    except subprocess.TimeoutExpired:
        return True, "Multiwfn launches (interactive prompt timeout is acceptable)."
    except Exception as exc:
        return False, f"Failed to launch Multiwfn: {exc}"

    if result.returncode in (0, 1):
        return True, "Multiwfn executable is reachable."
    return False, f"Multiwfn returned unexpected code: {result.returncode}"


def print_tool_setup_help():
    """Print quick setup help when ORCA/Multiwfn checks fail."""
    print("Quick setup guidance:")
    print("  1) Set orca_bin_path in config.json")
    print("  2) Set multiwfn_path in config.json")
    print("  3) Optional environment variables:")
    print('     export QMSEP_ORCA_BIN_PATH="/path/to/orca"')
    print('     export QMSEP_MULTIWFN_PATH="/path/to/Multiwfn_noGUI"')


def run_checks(config_path: str) -> int:
    """Run all checks and print a professional preflight report."""
    checks: List[Tuple[str, str, callable]] = [
        ("Project structure", "Verifies all required project files are present.", check_required_files),
        ("Python runtime", "Verifies Python scientific dependencies can be imported.", check_python_imports),
        ("Configuration file", "Parses config and verifies critical parameters.", lambda: check_config_validity(config_path)),
        ("ORCA integration", "Verifies ORCA binary executable access.", lambda: check_orca_connection(config_path)),
        ("Multiwfn integration", "Verifies Multiwfn executable availability and launch.", lambda: check_multiwfn_connection(config_path)),
    ]

    passed = 0
    print_qmsep_banner()
    for idx, (title, description, check_fn) in enumerate(checks, start=1):
        print(f"[Step {idx}/{len(checks)}] {title}")
        print(f"  - Check purpose: {description}")
        ok, message = check_fn()
        if ok:
            print(f"  - Result: {GREEN}PASS{RESET} | {message}")
            passed += 1
        else:
            print(f"  - Result: {RED}FAIL{RESET} | {message}")
            if title in ("ORCA integration", "Multiwfn integration"):
                print_tool_setup_help()
        print("-" * 72)

    print(f"Preflight summary: {passed}/{len(checks)} checks passed.")
    if passed == len(checks):
        print(f"{GREEN}Environment is ready for QMSEP production runs.{RESET}")
        return 0
    print(f"{RED}Please resolve failed checks before launching the production pipeline.{RESET}")
    return 1


def main():
    """CLI entry point."""
    config_path = "config.json"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    sys.exit(run_checks(config_path))


if __name__ == "__main__":
    main()
