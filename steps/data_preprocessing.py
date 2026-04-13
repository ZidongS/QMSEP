"""Prepare PQR data and ORCA input files for downstream calculations."""

import os
import subprocess
from typing import Dict, Tuple

class DataPreprocessor:
    """Handle PDB-to-PQR conversion and ORCA input generation."""
    
    def __init__(self, config: Dict, logger):
        self.config = config
        self.logger = logger
        self.pdb2pqr_force_field = config.get("pdb2pqr_force_field", "SWANSON")
        self.pqr_radius_scale = float(config.get("pqr_radius_scale", 1.2))
        self.orca_functional = config.get("orca_functional", "B3LYP")
        self.orca_basis_set = config.get("orca_basis_set", "6-31G*")
        self.orca_nprocs = int(config.get("orca_nprocs", 32))
        self.orca_maxcore = int(config.get("orca_maxcore", 7000))
    
    def process(self, pdb_id: str, temp_dir: str) -> Tuple[str, int, float]:
        """Process PDB ID to generate PQR and ORCA input files"""
        pqr_path = os.path.join(temp_dir, f"{pdb_id}.pqr")
        
        # Run pdb2pqr with configurable force field.
        try:
            subprocess.run([
                "pdb2pqr", "--drop-water", "--ff", self.pdb2pqr_force_field,
                pdb_id, pqr_path
            ], check=True, capture_output=True, text=True)
            self.logger.info(f"Successfully generated PQR file: {pqr_path}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"pdb2pqr failed: {e.stderr}")
            raise
        
        # Clean and overwrite PQR.
        atom_count, total_charge = self._clean_pqr(pqr_path)
        self.logger.info(f"Cleaned PQR file, found {atom_count} atoms, total charge {total_charge:.2f}")
        
        # Generate ORCA input files.
        self._generate_orca_inputs(pdb_id, temp_dir, pqr_path, atom_count, total_charge)
        self.logger.info("Generated ORCA input files")
        
        return pqr_path, atom_count, total_charge

    def _clean_pqr(self, file_path: str) -> Tuple[int, float]:
            """
            Clean PQR file, enforce 2500-atom limit for ORCA, and return atom count/total charge.
            Outputs in fixed-column width format (78 characters) including dielectric column.
            """
            processed_lines = []
            atom_count = 0
            total_charge = 0.0
            default_dielectric = 4.0000
            ATOM_LIMIT = 2500
            
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                        
                    if line.startswith("ATOM") or line.startswith("HETATM"):
                        parts = line.split()
                        if len(parts) < 9:
                            continue

                        # Count atoms and enforce ORCA size limit.
                        atom_count += 1
                        if atom_count > ATOM_LIMIT:
                            error_msg = f"Too many atoms for ORCA calculation. Limit is {ATOM_LIMIT}."
                            if hasattr(self, 'logger'):
                                self.logger.error(error_msg)
                            raise ValueError(error_msg)

                        # Parse core fields.
                        record_type = parts[0]
                        atom_serial = int(parts[1])
                        atom_name = parts[2]
                        residue_name = parts[3]

                        # Detect whether chain identifier exists in this row.
                        has_chain = False
                        try:
                            int(parts[4])
                            has_chain = False
                        except ValueError:
                            has_chain = True

                        if has_chain:
                            chain_id = parts[4]
                            residue_seq = int(parts[5])
                            x, y, z = float(parts[6]), float(parts[7]), float(parts[8])
                            charge = float(parts[9])
                            radius = float(parts[10])
                        else:
                            chain_id = " "
                            residue_seq = int(parts[4])
                            x, y, z = float(parts[5]), float(parts[6]), float(parts[7])
                            charge = float(parts[8])
                            radius = float(parts[9])

                        # Update summary statistics and basic radius safety check.
                        total_charge += charge
                        if radius == 0.0:
                            radius = 0
                            self.logger.error(f"Atom {atom_name} has radius 0.0")

                        # Apply conventional atom name formatting.
                        if len(atom_name) < 4:
                            atom_name_fmt = f" {atom_name:<3s}"
                        else:
                            atom_name_fmt = f"{atom_name:<4s}"

                        # Rebuild line using strict fixed-width columns.
                        new_line = (
                            f"{record_type:<6s}"              # 1-6
                            f"{atom_serial:>5d}"              # 7-11
                            f" "                               # 12
                            f"{atom_name_fmt}"                 # 13-16
                            f"{residue_name:>4s}"              # 17-20
                            f" "                               # 21
                            f"{chain_id:1s}"                   # 22
                            f"{residue_seq:>4d}"               # 23-26
                            f"    "                            # 27-30
                            f"{x:>8.3f}"                       # 31-38
                            f"{y:>8.3f}"                       # 39-46
                            f"{z:>8.3f}"                       # 47-54
                            f"{charge:>8.4f}"                  # 55-62
                            f"{radius:>8.4f}"                  # 63-70
                            f"{default_dielectric:>8.4f}\n"    # 71-78
                        )
                        processed_lines.append(new_line)
                    else:
                        # Preserve non-atom records, such as TER and END.
                        processed_lines.append(line + "\n")
            
            # Write cleaned data back into the same file.
            with open(file_path, 'w') as f:
                f.writelines(processed_lines)
                
            return atom_count, total_charge

    def _generate_orca_inputs(self, pdb_id: str, temp_dir: str, pqr_path: str, atom_count: int, total_charge: float):
        atoms_geometry = []
        atoms_radii_lines = []
        
        with open(pqr_path, 'r') as f:
            atom_index = 0
            for line in f:
                if not (line.startswith("ATOM") or line.startswith("HETATM")):
                    continue
                    
                parts = line.split()
                # Parse from the end to avoid column shifts when chain ID is missing.
                try:
                    radius = float(parts[-2]) * self.pqr_radius_scale
                    charge = float(parts[-3])
                    z = parts[-4]
                    y = parts[-5]
                    x = parts[-6]
                    # Derive atomic symbol in a robust way for ORCA geometry.
                    atom_symbol = parts[2][0] if not parts[2][0].isdigit() else parts[1][0]
                except (IndexError, ValueError) as e:
                    self.logger.warning(f"Skipping malformed line: {line.strip()}")
                    continue

                atoms_geometry.append(f"{atom_symbol} {x} {y} {z}")
                atoms_radii_lines.append(f"   AtomRadii({atom_index}, {radius})")
                atom_index += 1

        final_charge = int(round(total_charge))
        multiplicity = 1
        
        # Gas phase ORCA input.
        gas_inp_path = os.path.join(temp_dir, f"{pdb_id}_gas.inp")
        with open(gas_inp_path, 'w') as f:
            f.write(f"! {self.orca_functional} {self.orca_basis_set}\n")
            f.write(f"%pal\nnprocs {self.orca_nprocs}\nend\n")
            f.write(f"%maxcore {self.orca_maxcore}\n")
            f.write(f"* xyz {final_charge} {multiplicity}\n")
            f.writelines([line + "\n" for line in atoms_geometry])
            f.write("*\n")
        
        # Solvated phase ORCA input.
        solv_inp_path = os.path.join(temp_dir, f"{pdb_id}_solv.inp")
        with open(solv_inp_path, 'w') as f:
            f.write(f"! {self.orca_functional} {self.orca_basis_set} CPCM(water)\n")
            f.write(f"%pal\nnprocs {self.orca_nprocs}\nend\n")
            f.write(f"%maxcore {self.orca_maxcore}\n")
            f.write("%cpcm\n")
            f.writelines([line + "\n" for line in atoms_radii_lines])
            f.write("end\n")
            f.write(f"* xyz {final_charge} {multiplicity}\n")
            f.writelines([line + "\n" for line in atoms_geometry])
            f.write("*\n")