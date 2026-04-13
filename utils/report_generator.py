"""Generate run reports with timing, parameter, and provenance details."""

from typing import List, Dict
from datetime import datetime
from pathlib import Path

class ReportGenerator:
    """Generate per-run and per-PDB reports."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.output_dir = Path(config['output_dir'])
        self.step_descriptions = {
            "data_preprocessing": "Convert PDB to cleaned PQR and generate ORCA input decks.",
            "orca_calculations": "Run ORCA gas/solv calculations through Apptainer container.",
            "charge_extraction": "Extract reacting charge model from ORCA electronic structure output.",
            "point_sampling": "Sample molecular surface points in selected surface mode.",
            "potential_calculation": "Compute electrostatic potential at sampled points with Multiwfn.",
        }
    
    def generate_report(self, results: List[Dict], total_time: float) -> str:
        """Generate a summary report."""
        report_file = self.output_dir / f"pipeline_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        with open(report_file, 'w') as f:
            f.write("="*60 + "\n")
            f.write("PIPELINE EXECUTION REPORT\n")
            f.write("="*60 + "\n")
            f.write(f"Report generated at: {datetime.now()}\n")
            f.write(f"Task start time: {self.config.get('task_start_time', 'N/A')}\n")
            f.write(f"Total execution time: {total_time:.2f}s\n")
            f.write(f"Total PDBs processed: {len(results)}\n")
            f.write("\nRuntime parameters:\n")
            for key, description in self.config.get("parameter_descriptions", {}).items():
                f.write(f"  - {key}: {self.config.get(key)}\n")
                f.write(f"      {description}\n")
            f.write("\n")
            
            for result in results:
                f.write("-"*40 + "\n")
                f.write(f"PDB ID: {result['pdb_id']}\n")
                f.write(f"Status: {result['status']}\n")
                
                if result['status'] == 'success':
                    total_step_time = sum(result['step_times'].values())
                    f.write(f"Total time: {total_step_time:.2f}s\n")
                    f.write(f"Atom count: {result['atom_count']}\n")
                    f.write(f"Total charge: {result['total_charge']}\n")
                    
                    if result['potential_stats']:
                        stats = result['potential_stats']
                        f.write(f"Potential (min/max/mean): {stats['min']:.4f} / {stats['max']:.4f} / {stats['mean']:.4f}\n")
                    
                    f.write("\nStep times:\n")
                    for step, time in result['step_times'].items():
                        desc = self.step_descriptions.get(step, "No description available.")
                        f.write(f"  - {step}: {time:.2f}s\n")
                        f.write(f"      {desc}\n")
                else:
                    f.write(f"Error: {result['error']}\n")
                
                f.write("\n")
        
        return str(report_file)