"""Compute electrostatic potential labels using Multiwfn."""

import os
import subprocess

class PotentialCalculator:
    """Calculate potentials using Multiwfn."""
    
    def __init__(self, config: dict, logger):
        self.config = config
        self.logger = logger
        self.multiwfn_path = config.get('multiwfn_path', '/mnt/sda2/szd/Multiwfn_3.8_dev_bin_Linux_noGUI/Multiwfn_noGUI')
    
    def calculate(self, pdb_id: str, temp_dir: str) -> str:
        """Calculate potentials using Multiwfn"""
        gbw_file = os.path.join(temp_dir, f"{pdb_id}_solv.gbw")
        surface_file = os.path.join(temp_dir, f"{pdb_id}_surface_bohr.txt")
        
        if not os.path.exists(gbw_file):
            raise FileNotFoundError(f"ORCA solv GBW file not found: {gbw_file}")
        
        if not os.path.exists(surface_file):
            raise FileNotFoundError(f"Surface points file not found: {surface_file}")
        
        # Output files
        reacting_chg = os.path.join(temp_dir, f"{pdb_id}_reacting_charge.chg")
        surface_txt = os.path.join(temp_dir, f"{pdb_id}_surface_bohr.txt")
        checkpoint_txt = os.path.join(temp_dir, f"{pdb_id}_checkpoint_label.txt")
        
        # Create Multiwfn input script
        input_script = self._create_multiwfn_input_script(reacting_chg, surface_txt, checkpoint_txt)
        
        # Write temporary input file
        input_script_path = os.path.join(temp_dir, f"{pdb_id}_multiwfn_input.txt")
        with open(input_script_path, 'w') as f:
            f.write(input_script)
        
        # Run Multiwfn
        try:
            self.logger.info(f"Running Multiwfn for {pdb_id}")
            
            with open(input_script_path, 'r') as f_in:
                result = subprocess.run(
                    [self.multiwfn_path, gbw_file],
                    stdin=f_in,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
            
            if result.returncode == 0:
                self.logger.success("Multiwfn completed successfully")
                if os.path.exists(checkpoint_txt):
                    return checkpoint_txt
                else:
                    raise RuntimeError("Multiwfn completed but checkpoint file not found")
            else:
                self.logger.error(f"Multiwfn failed: {result.stderr}")
                raise RuntimeError(f"Multiwfn execution failed: {result.stderr}")
                
        finally:
            # Cleanup temporary input file
            if os.path.exists(input_script_path):
                #os.remove(input_script_path)
                print("Multiwfn input script saved")
    
    def _create_multiwfn_input_script(self, reacting_chg: str, surface_txt: str, checkpoint_txt: str) -> str:
        """Create Multiwfn input script"""
        commands = [
            "5",  
            "0",  
            "1",  
            f"+,{reacting_chg}",  
            "12", 
            "100", 
            surface_txt, 
            checkpoint_txt,  
            "q"   
        ]
        
        return "\n".join(commands) + "\n"