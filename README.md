<div align="center">
  <img src="https://github.com/user-attachments/assets/58ddfb3b-2af7-4946-9c81-b28e7e526722" alt="QMSEP Logo" width="500">

  <h1>QMSEP (v1.0.0)</h1>

  <p><b>Quantum Mechanics Surface Electrostatic Potential (QMSEP) workflow for next-level molecular surface potential calculations.</b></p>
  <p><b>Just need PDBID as input, QMSEP handles all the rest for you!</b></p>
  <p>
    <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.x-blue.svg" alt="Python 3.x"></a>
  </p>
</div>

---

## Table of Contents
- [Overview](#overview)
- [Installation](#installation)
- [Setup & Registration](#setup--registration)
- [Preflight Check](#preflight-check)
- [Quick Start](#quick-start)
- [Configuration Precedence](#configuration-precedence)
- [Configuration Parameters and CLI Reference](#configuration-parameters-and-cli-reference)
- [Output Structure](#output-structure)
- [Citations & Acknowledgements](#citations--acknowledgements)

---

## Overview

**QMSEP** automates the workflow for calculating dielectric charges through surface electrostatic potentials. The automated pipeline includes:

1. **PDB to PQR preprocessing**
2. **ORCA gas and solvated electronic structure calculations**
3. **Reacting charge extraction**
4. **Surface point sampling** (`vdw`, `ses`, `eps`)
5. **Multiwfn electrostatic potential labeling**

## Installation

### Python Environment

It is highly recommended to use Conda for environment management:

```bash
git clone https://github.com/ZidongS/QMSEP.git
cd ./QMSEP
conda env create -f env.yaml
conda activate qmsep
```

Alternatively, you can install dependencies via `pip`:

```bash
pip install numpy scipy scikit-image pdb2pqr
```

### External Tools

You must install the following external tools before running QMSEP:

- **ORCA**: ORCA is a powerful, modern quantum chemistry software package. QMSEP use ORCA to calculate wavefunction of molecular of interest.You can download ORCA here [ORCA Download](https://www.faccts.de/customer "ORCA Download")
  ```bash
  #quick download command for linux user
  cd QMSEP
  mkdir -p ./orca_install
  cd ./orca_install
  # download and save orca_6_1_1_linux_x86-64_shared_openmpi418_nodmrg.tar.xz
  conda install -c conda-forge openmpi=4.1 libstdcxx-ng -y
  tar -xJf orca_6_1_1_linux_x86-64_shared_openmpi418_nodmrg.tar.xz
  rm orca_6_1_1_linux_x86-64_shared_openmpi418_nodmrg.tar.xz
  ```                                          
- **Multiwfn**: Multiwfn is a powerful program for realizing electronic wavefunction analysis. QMSEP use Multiwfn to analysis wavefunction and calculate potential.
You can download Multiwfn here [Multiwfn Download](http://sobereva.com/multiwfn/ "Multiwfn Download")
   ```bash
  #quick download command for linux user
  cd QMSEP
  mkdir -p ./multiwfn_install
  cd ./multiwfn_install
  wget http://sobereva.com/multiwfn/misc/Multiwfn_2026.4.10_bin_Linux_noGUI.zip
  unzip Multiwfn_2026.4.10_bin_Linux_noGUI.zip
  rm Multiwfn_2026.4.10_bin_Linux_noGUI.zip
  ``` 
> **💡 Tip:**
> - If ORCA is already added to your system's `PATH`, you can simply set `"orca_bin_path": "orca"`.
> - Otherwise, you must provide the full absolute path (e.g., `/opt/orca/orca`).
> - You also need to edit the settings.ini file in multiwfn folder and set `orca_2mklpath` and `nthreads`.

## Setup & Registration

If you prefer not to pass the `--config` flag every time, you can register the paths to your external tools globally from the command line:

```bash
python pipeline_orchestrator.py --register-orca-bin-path "/path/to/orca"
python pipeline_orchestrator.py --register-multiwfn-path "/path/to/Multiwfn_noGUI"
```

These values are saved securely in `~/.qmsep_cli_config.json` and will be reused automatically in future runs.

Alternatively, you can use environment variables:

```bash
export QMSEP_ORCA_BIN_PATH="/path/to/orca"
export QMSEP_MULTIWFN_PATH="/path/to/Multiwfn_noGUI"
```

## Preflight Check

Before running your first actual calculation, it is highly recommended to perform a preflight check to ensure your environment is configured correctly:

```bash
python qmsep_preflight.py
```

Or, if you are using a custom configuration file:

```bash
python qmsep_preflight.py custom_config.json
```

**The preflight sequence verifies:**
1. Project structure integrity
2. Python dependencies availability
3. Configuration parsing and required keys
4. ORCA binary accessibility
5. Multiwfn executable accessibility

> **Note:** `python test_pipeline.py` is preserved as a legacy alias for this command.

## Quick Start

**Single PDB processing:**
```bash
python pipeline_orchestrator.py 2RVD
```

**Multiple PDB processing (Parallel):**
```bash
python pipeline_orchestrator.py 2RVD 2JOF 7SOH --parallel --max-workers 4
```

**Using a custom JSON configuration:**
```bash
python pipeline_orchestrator.py 2RVD --config custom_config.json
```

## Configuration Precedence

QMSEP resolves configuration parameters using the following priority hierarchy (from lowest to highest):

1. **Built-in defaults** (Lowest)
2. Project `config.json`
3. User registration file `~/.qmsep_cli_config.json`
4. `--config` file passed at runtime
5. **CLI explicit arguments** (Highest)

## Configuration Parameters and CLI Reference

The following table provides a comprehensive reference for all supported configuration parameters. These settings can be defined in a configuration file or overridden at runtime using the corresponding CLI arguments with `pipeline_orchestrator.py`.

| Parameter (Config) | CLI Argument | Type | Default | Options / Valid Values | Description |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `multiwfn_path` | `--multiwfn-path` | `string` | `$QMSEP_MULTIWFN_PATH` | - | Path to the Multiwfn executable. |
| `orca_bin_path` | `--orca-bin-path` | `string` | `orca` | - | Path to the ORCA executable (or `$QMSEP_ORCA_BIN_PATH`). |
| `max_retries` | - | `int` | `1` | - | Number of ORCA execution retry attempts. |
| `retry_delay` | - | `int` | `5` | - | Sleep time (in seconds) between retry attempts. |
| `surface_mode` | `--surface-mode` | `string` | `ses` | `vdw`, `ses`, `eps` | Method used for surface generation. |
| `sample_points` | `--sample-points` | `int` | `10000` | - | Target number of sampled surface points. |
| `grid_spacing` | `--grid-spacing` | `float` | `0.1` | - | Grid spacing dimension in Angstroms. |
| `log_level` | `--log-level` | `string` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | System console log output level. |
| `keep_intermediates`| `--keep-intermediates`| `bool` | `false` | `true`, `false` | Whether to retain temporary intermediate files after a run. |
| `output_dir` | `--output-dir` | `string` | `output` | - | Root directory for output generation. |
| `temp_dir` | `--temp-dir` | `string` | `temp` | - | Root directory for temporary file storage. |
| `pdb2pqr_force_field`| `--pdb2pqr-force-field`| `string` | `SWANSON` | `AMBER`, `CHARMM`, `PARSE`, `TYL06`, `PEOEPB`, `SWANSON` | Force field standard used for `pdb2pqr`. |
| `pqr_radius_scale` | `--pqr-radius-scale` | `float` | `1.2` | - | Cavity radius scaling factor used in ORCA input generation. |
| `orca_functional` | `--orca-functional` | `string` | `B3LYP` | - | Density Functional (DFT) chosen for ORCA. |
| `orca_basis_set` | `--orca-basis-set` | `string` | `6-31G*` | - | Basis set chosen for ORCA calculations. |
| `orca_nprocs` | `--orca-nprocs` | `int` | `32` | - | Number of processors for ORCA (`%pal nprocs`). |
| `orca_maxcore` | `--orca-maxcore` | `int` | `7000` | - | Maximum memory per core for ORCA in MB (`%maxcore`). |
| `eps_gaussian_exponent`| `--eps-gaussian-exponent`| `float` | `5.0` | - | EPS density exponent (Only effective when `surface_mode=eps`). |
| `eps_target_iso_level` | `--eps-target-iso-level` | `float` | `0.999` | - | EPS target isovalue (Only effective when `surface_mode=eps`). |

---

### Runtime-Only CLI Arguments

These arguments are used to control the orchestration behavior or register environment paths and are not typically stored in static configuration files:

* **Execution Control:**
    * `--config FILE`: Path to the configuration file to be loaded.
    * `--parallel`: Enable parallel processing for multiple tasks.
    * `--max-workers N`: Specify the maximum number of concurrent workers.
* **Environment Registration:**
    * `--register-orca-bin-path PATH`: Register and persist the ORCA executable path.
    * `--register-multiwfn-path PATH`: Register and persist the Multiwfn executable path.

## Output Structure

Upon completion, QMSEP generates the following organized structure in your specified output directory:

```text
output/
├── pipeline_report_*.txt          # Global execution report across all PDBs
├── <PDB_ID>/
│   ├── pipeline.log               # Detailed runtime log specific to this PDB
│   ├── run_context.txt            # Effective parameters and step context
│   └── (Generated Outputs)        # Specific PQR, ORCA, and Multiwfn related files
```

## Citations & Acknowledgements

If you use this software in your research, please consider citing the underlying tools:

- **ORCA:** Neese, F. (2012). *WIREs Computational Molecular Science*, 2(1), 73-78. [DOI: 10.1002/wcms.81](https://doi.org/10.1002/wcms.81)
- **Multiwfn (Original):** Tian Lu, Feiwu Chen, *J. Comput. Chem.* 33, 580-592 (2012). [DOI: 10.1002/jcc.22885](https://doi.org/10.1002/jcc.22885)
- **Multiwfn (Updates):** Tian Lu, *J. Chem. Phys.* 161, 082503 (2024). [DOI: 10.1063/5.0216272](https://doi.org/10.1063/5.0216272)
