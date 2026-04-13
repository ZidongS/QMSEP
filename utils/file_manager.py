"""Manage temporary and output file paths for pipeline tasks."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List

class FileManager:
    """Handle file and directory operations for pipeline runs."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.output_dir = Path(config['output_dir'])
        self.output_dir.mkdir(exist_ok=True)
    
    def create_temp_directory(self, pdb_id: str) -> str:
        """Create a temporary directory for a PDB ID"""
        if self.config.get('temp_dir'):
            base_temp_dir = Path(self.config['temp_dir'])
            base_temp_dir.mkdir(exist_ok=True)
            temp_dir = base_temp_dir / f"temp_{pdb_id}"
            temp_dir.mkdir(exist_ok=True)
            return str(temp_dir)
        else:
            return tempfile.mkdtemp(prefix=f"temp_{pdb_id}_")
    
    def cleanup_temp_directory(self, temp_dir: str):
        """Remove a temporary directory"""
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    def save_output_files(self, pdb_id: str, files_to_copy: List[str]) -> List[str]:
        """
        Copies a list of files to a dedicated subdirectory in the main output folder.
        The subdirectory will be named after the PDB ID.
        """
        pdb_output_dir = self.output_dir / pdb_id
        pdb_output_dir.mkdir(exist_ok=True)
        
        saved_files = []
        for src_path in files_to_copy:
            if src_path and os.path.exists(src_path):
                try:
                    dest_path = pdb_output_dir / os.path.basename(src_path)
                    shutil.copy(src_path, dest_path)
                    saved_files.append(str(dest_path))
                except (IOError, OSError) as e:
                    # This should ideally use the logger, but for now, we print a warning.
                    print(f"[Warning] Could not copy {src_path} to {pdb_output_dir}: {e}")
        
        return saved_files

    def get_pdb_output_dir(self, pdb_id: str) -> Path:
        """Return the output directory path for a specific PDB ID."""
        pdb_output_dir = self.output_dir / pdb_id
        pdb_output_dir.mkdir(parents=True, exist_ok=True)
        return pdb_output_dir
