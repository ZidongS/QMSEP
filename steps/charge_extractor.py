import os

class ChargeExtractor:
    """Extracts reacting charges from ORCA output"""
    
    def __init__(self, config: dict, logger):
        self.config = config
        self.logger = logger
    
    def extract(self, pdb_id: str, temp_dir: str) -> str:
        """Extract reacting charges from ORCA solv output"""
        solv_out = os.path.join(temp_dir, f"{pdb_id}_solv.cpcm")
        charge_file = os.path.join(temp_dir, f"{pdb_id}_reacting_charge.chg")
        
        if not os.path.exists(solv_out):
            raise FileNotFoundError(f"ORCA solv output file not found: {solv_out}")
        
        points_data = []
        is_reading = False
        
        with open(solv_out, 'r') as f:
            for line in f:
                if "SURFACE POINTS (A.U.)" in line:
                    is_reading = True
                    continue
                
                if is_reading:
                    if "-------" in line or "X" in line:
                        continue
                    if not line.strip() or ("CPCM" in line and "Energy" in line):
                        if len(points_data) > 0:
                            break
                        else:
                            continue
                    
                    parts = line.split()
                    try:
                        x_au = float(parts[0])
                        y_au = float(parts[1])
                        z_au = float(parts[2])
                        q_raw = float(parts[5])
                        
                        # Apply dielectric scaling
                        epsilon = 80.4
                        f_eps = (epsilon - 1.0) / epsilon
                        bohr_to_ang = 0.52917721
                        
                        x_ang = x_au * bohr_to_ang
                        y_ang = y_au * bohr_to_ang
                        z_ang = z_au * bohr_to_ang
                        q_scaled = q_raw * f_eps
                        
                        points_data.append((x_ang, y_ang, z_ang, q_scaled))
                    except (ValueError, IndexError):
                        if len(points_data) > 0:
                            break
        
        # Write charge file
        with open(charge_file, 'w') as out:
            for p in points_data:
                out.write(f"Bq   {p[0]:12.6f} {p[1]:12.6f} {p[2]:12.6f} {p[3]:12.6f}\n")
        
        self.logger.info(f"Extracted {len(points_data)} surface point charges")
        return charge_file