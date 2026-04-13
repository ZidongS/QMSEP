"""Run ORCA gas and solvated jobs with retry support."""

import os
import subprocess
import time
import shutil
from typing import Dict, Optional

class OrcaRunner:
    """Handle ORCA calculations."""
    
    def __init__(self, config: Dict, logger):
        self.config = config
        self.logger = logger
        self.max_retries = config.get('max_retries', 1)
        self.retry_delay = config.get('retry_delay', 5)
        self.orca_bin_path = config.get('orca_bin_path', 'orca')
    
    def run(self, pdb_id: str, temp_dir: str) -> Dict[str, Optional[str]]:
        """Run ORCA calculations for a PDB ID and return output file paths."""
        results = {}
        
        input_files = [
            os.path.join(temp_dir, f"{pdb_id}_gas.inp"),
            os.path.join(temp_dir, f"{pdb_id}_solv.inp")
        ]
        
        for inp_file in input_files:
            if os.path.exists(inp_file):
                suffix = "gas" if "gas" in inp_file else "solv"
                self.logger.info(f"Running ORCA {suffix} calculation for {pdb_id}")
                self.logger.info(f"ORCA binary path: {self.orca_bin_path}")
                
                output_path = self._run_orca_job(inp_file, temp_dir, suffix)
                results[suffix] = output_path
                
                if output_path:
                    self.logger.success(f"ORCA {suffix} calculation completed: {os.path.basename(output_path)}")
                else:
                    self.logger.warning(f"ORCA {suffix} calculation failed after {self.max_retries + 1} attempts")
        
        return results
    
    def _run_orca_job(self, inp_file: str, temp_dir: str, suffix: str) -> Optional[str]:
        """Run a single ORCA job with retry logic and return the output file path on success."""
        base_name = os.path.basename(inp_file).replace('.inp', '')
        
        for attempt in range(self.max_retries + 1):
            out_file = os.path.join(temp_dir, f"{base_name}_try{attempt}.out" if attempt > 0 else f"{base_name}.out")

            try:
                self.logger.info(f"Attempt {attempt + 1}/{self.max_retries + 1}: Running ORCA {suffix}")
                with open(out_file, "w", encoding="utf-8") as out_f:
                    subprocess.run(
                        [self.orca_bin_path, inp_file, "--oversubscribe"],
                        check=True,
                        stdout=out_f,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                
                if os.path.exists(out_file):
                    with open(out_file, 'r', errors='ignore') as f:
                        if "ORCA TERMINATED NORMALLY" in f.read():
                            final_out_file = os.path.join(temp_dir, f"{base_name}.out")
                            if out_file != final_out_file:
                                shutil.move(out_file, final_out_file)
                            return final_out_file
                
                if attempt < self.max_retries:
                    self.logger.warning(f"Attempt {attempt + 1} failed, retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                    
            except subprocess.CalledProcessError as e:
                self.logger.error(f"ORCA {suffix} attempt {attempt + 1} failed: {e.stderr}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
        
        return None
