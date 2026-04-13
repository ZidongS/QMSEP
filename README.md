# QMSEP (v1.0.0)

Quantum Mechanics Surface Electrostatic Potential (QMSEP) workflow for dielectric-charge calculations.

Author: Zidong Shu  
License: MIT

## 1) What QMSEP does

QMSEP automates:
1. PDB to PQR preprocessing
2. ORCA gas and solvated electronic structure calculations
3. Reacting charge extraction
4. Surface point sampling (`vdw`, `ses`, `eps`)
5. Multiwfn electrostatic potential labeling

## 2) Install dependencies

### Python environment

Use Conda (recommended):
```bash
conda env create -f env.yaml
conda activate qmsep
```

Or pip:
```bash
pip install numpy scipy scikit-image pdb2pqr
```

### External tools (install these first)

- `ORCA` binary executable (must be callable from terminal)
- `Multiwfn` executable
- `pdb2pqr`

Tip:
- If ORCA is in PATH, set `"orca_bin_path": "orca"`.
- Otherwise use full absolute path, such as `/opt/orca/orca`.

## 3) Register ORCA and Multiwfn once

If users do not want `--config`, register paths from command line:

```bash
python pipeline_orchestrator.py --register-orca-bin-path "/path/to/orca"
python pipeline_orchestrator.py --register-multiwfn-path "/path/to/Multiwfn_noGUI"
```

These values are saved in `~/.qmsep_cli_config.json` and reused automatically.

You can also set environment variables:
```bash
export QMSEP_ORCA_BIN_PATH="/path/to/orca"
export QMSEP_MULTIWFN_PATH="/path/to/Multiwfn_noGUI"
```

## 4) Recommended preflight (before quick start)

Run:
```bash
python qmsep_preflight.py
```

Or with custom config:
```bash
python qmsep_preflight.py custom_config.json
```

Checks include:
1. Project structure integrity
2. Python dependencies
3. Config parse and required keys
4. ORCA binary accessibility
5. Multiwfn accessibility

Legacy alias:
```bash
python test_pipeline.py
```

## 5) Quick start

Single PDB:
```bash
python pipeline_orchestrator.py 2RVD
```

Multiple PDB:
```bash
python pipeline_orchestrator.py 2RVD 2JOF 7SOH --parallel --max-workers 4
```

Custom config:
```bash
python pipeline_orchestrator.py 2RVD --config custom_config.json
```

## 6) Configuration precedence

Priority from low to high:
1. Built-in defaults
2. Project `config.json`
3. User registration file `~/.qmsep_cli_config.json`
4. `--config` file
5. CLI explicit arguments

## 7) Full config parameter reference

- `multiwfn_path`  
  - Type: `string`  
  - Default: env `QMSEP_MULTIWFN_PATH` or built-in path  
  - Meaning: path to Multiwfn executable

- `orca_bin_path`  
  - Type: `string`  
  - Default: env `QMSEP_ORCA_BIN_PATH` or `orca`  
  - Meaning: path to ORCA executable

- `max_retries`  
  - Type: `int`  
  - Default: `1`  
  - Meaning: ORCA retry attempts

- `retry_delay`  
  - Type: `int` (seconds)  
  - Default: `5`  
  - Meaning: sleep time between retries

- `surface_mode`  
  - Type: `string`  
  - Options: `vdw`, `ses`, `eps`  
  - Default: `ses`  
  - Meaning: surface generation mode

- `sample_points`  
  - Type: `int`  
  - Default: `10000`  
  - Meaning: number of sampled surface points

- `grid_spacing`  
  - Type: `float`  
  - Default: `0.1`  
  - Meaning: grid spacing in angstrom

- `log_level`  
  - Type: `string`  
  - Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`  
  - Default: `INFO`  
  - Meaning: runtime log level

- `keep_intermediates`  
  - Type: `bool`  
  - Default: `false`  
  - Meaning: keep temp files if true

- `output_dir`  
  - Type: `string`  
  - Default: `output`  
  - Meaning: output root directory

- `temp_dir`  
  - Type: `string`  
  - Default: `temp`  
  - Meaning: temp root directory

- `pdb2pqr_force_field`  
  - Type: `string`  
  - Options: `AMBER`, `CHARMM`, `PARSE`, `TYL06`, `PEOEPB`, `SWANSON`  
  - Default: `SWANSON`  
  - Meaning: force field for `pdb2pqr`

- `pqr_radius_scale`  
  - Type: `float`  
  - Default: `1.2`  
  - Meaning: cavity radius scaling in ORCA input generation

- `orca_functional`  
  - Type: `string`  
  - Default: `B3LYP`  
  - Meaning: ORCA DFT functional

- `orca_basis_set`  
  - Type: `string`  
  - Default: `6-31G*`  
  - Meaning: ORCA basis set

- `orca_nprocs`  
  - Type: `int`  
  - Default: `32`  
  - Meaning: ORCA `%pal nprocs`

- `orca_maxcore`  
  - Type: `int`  
  - Default: `7000`  
  - Meaning: ORCA `%maxcore` (MB/core)

- `eps_gaussian_exponent`  
  - Type: `float`  
  - Default: `5.0`  
  - Meaning: EPS density exponent (effective when `surface_mode=eps`)

- `eps_target_iso_level`  
  - Type: `float`  
  - Default: `0.999`  
  - Meaning: EPS target isovalue (effective when `surface_mode=eps`)

## 8) Main CLI options

- `--config FILE`
- `--parallel --max-workers N`
- `--output-dir DIR`
- `--temp-dir DIR`
- `--keep-intermediates`
- `--surface-mode {vdw,ses,eps}`
- `--sample-points INT`
- `--grid-spacing FLOAT`
- `--log-level {DEBUG,INFO,WARNING,ERROR}`
- `--multiwfn-path PATH`
- `--orca-bin-path PATH`
- `--pdb2pqr-force-field {AMBER,CHARMM,PARSE,TYL06,PEOEPB,SWANSON}`
- `--pqr-radius-scale FLOAT`
- `--orca-functional STR`
- `--orca-basis-set STR`
- `--orca-nprocs INT`
- `--orca-maxcore INT`
- `--eps-gaussian-exponent FLOAT`
- `--eps-target-iso-level FLOAT`
- `--register-orca-bin-path PATH`
- `--register-multiwfn-path PATH`

## 9) Output

- `output/pipeline_report_*.txt`: global run report
- `output/<PDB_ID>/pipeline.log`: per-PDB runtime log
- `output/<PDB_ID>/run_context.txt`: effective params and step context
- generated calculation outputs (PQR/ORCA/Multiwfn related files)

## 10) Citation and acknowledgement

- ORCA: Neese, F. (2012). *WIREs Computational Molecular Science*, 2(1), 73-78. DOI: 10.1002/wcms.81
- Multiwfn: Tian Lu, Feiwu Chen, *J. Comput. Chem.* 33, 580-592 (2012). DOI: 10.1002/jcc.22885
- Multiwfn: Tian Lu, *J. Chem. Phys.* 161, 082503 (2024). DOI: 10.1063/5.0216272