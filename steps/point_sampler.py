"""Generate molecular surface points using VDW, SES, or EPS modes."""

import numpy as np
import os
from typing import List, Dict
from scipy.spatial import KDTree
from scipy.spatial.distance import cdist
from skimage import measure


class PointSampler:
    """
    Three-mode surface sampler:
      - 'vdw': van der Waals shell surface.
      - 'ses': solvent excluded surface (marching cubes on SES field).
      - 'eps': dielectric continuum surface (marching cubes on rho_mol field).

    Field sign convention for VDW/SES:
      phi < 0: inside molecule
      phi = 0: surface
      phi > 0: solvent side
    """

    def __init__(self, config: Dict, logger):
        self.config = config
        self.logger = logger

        self.surface_mode = config.get('surface_mode', 'vdw')   # 'vdw' | 'ses' | 'eps'
        self.sample_points = config.get('sample_points', 4000)
        self.grid_spacing = config.get('grid_spacing', 0.1)     # angstrom

        # VDW mode only.
        self.vdw_shell_thickness = config.get('vdw_shell_thickness', -0.1)  # angstrom
        self.vdw_min_distance = config.get('vdw_min_distance', -0.2)        # angstrom
        
        # SES mode only.
        self.probe_radius = config.get('probe_radius', 1.4)      # angstrom

        # EPS mode only.
        self.eps_gaussian_exponent = float(config.get('eps_gaussian_exponent', 5.0))
        self.eps_target_iso_level = float(config.get('eps_target_iso_level', 0.999))

        if self.surface_mode not in ('vdw', 'ses', 'eps'):
            raise ValueError(
                f"Unknown surface_mode '{self.surface_mode}'. "
                "Choose 'vdw', 'ses', or 'eps'."
            )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def sample(self, pdb_id: str, temp_dir: str) -> List[str]:
        pqr_path = os.path.join(temp_dir, f"{pdb_id}.pqr")
        if not os.path.exists(pqr_path):
            raise FileNotFoundError(f"PQR file not found: {pqr_path}")

        atoms = self._parse_pqr(pqr_path)
        self.logger.info(
            f"[{self.surface_mode.upper()}] Found {len(atoms)} atoms."
        )

        if self.surface_mode == 'vdw':
            surface_points = self._generate_vdw_points(atoms)
        elif self.surface_mode == 'ses':
            surface_points = self._generate_ses_points(atoms)
        else:
            surface_points = self._generate_eps_points(atoms)

        self.logger.info(
            f"Generated {len(surface_points)} surface points "
            f"(mode={self.surface_mode})."
        )

        ang_file = os.path.join(temp_dir, f"{pdb_id}_surface_ang.txt")
        bohr_file = os.path.join(temp_dir, f"{pdb_id}_surface_bohr.txt")
        self._save_surface_points(surface_points, ang_file, bohr_file)
        return [ang_file, bohr_file]

    # ------------------------------------------------------------------ #
    # PQR parsing
    # ------------------------------------------------------------------ #

    def _parse_pqr(self, pqr_path: str) -> List[Dict]:
        atoms = []
        with open(pqr_path, 'r') as f:
            for line in f:
                if line.startswith("ATOM") or line.startswith("HETATM"):
                    parts = line.split()
                    try:
                        atoms.append({
                            'coord': np.array([
                                float(parts[5]),
                                float(parts[6]),
                                float(parts[7])
                            ]),
                            'radius': float(parts[9])
                        })
                    except (ValueError, IndexError):
                        continue
        return atoms

    # ------------------------------------------------------------------ #
    # Shared helper: build VDW signed distance field
    # ------------------------------------------------------------------ #

    def _build_vdw_field(
        self,
        pts_3d: np.ndarray,
        coords: np.ndarray,
        radii: np.ndarray,
        chunk_size: int = 500_000
    ) -> np.ndarray:
        phi_vdW = np.full(len(pts_3d), np.inf, dtype=np.float32)
        for i in range(len(coords)):
            for start in range(0, len(pts_3d), chunk_size):
                end = min(start + chunk_size, len(pts_3d))
                dist = np.linalg.norm(pts_3d[start:end] - coords[i], axis=1)
                phi_vdW[start:end] = np.minimum(
                    phi_vdW[start:end],
                    dist - radii[i]
                )
        return phi_vdW

    # ================================================================== #
    # Mode 1: VDW surface sampling
    # ================================================================== #

    def _generate_vdw_points(self, atoms: List[Dict]) -> np.ndarray:
        coords = np.array([a['coord'] for a in atoms])
        radii = np.array([a['radius'] for a in atoms])

        padding = np.max(radii) + self.vdw_shell_thickness + 1.0
        min_bounds = np.min(coords, axis=0) - padding
        max_bounds = np.max(coords, axis=0) + padding

        nx = int(np.ceil((max_bounds[0] - min_bounds[0]) / self.grid_spacing))
        ny = int(np.ceil((max_bounds[1] - min_bounds[1]) / self.grid_spacing))
        nz = int(np.ceil((max_bounds[2] - min_bounds[2]) / self.grid_spacing))

        self.logger.info(
            f"[vdW] Grid: {nx}×{ny}×{nz} = {nx*ny*nz:,} voxels, "
            f"spacing={self.grid_spacing} Å"
        )

        x_1d = min_bounds[0] + np.arange(nx) * self.grid_spacing
        y_1d = min_bounds[1] + np.arange(ny) * self.grid_spacing
        z_1d = min_bounds[2] + np.arange(nz) * self.grid_spacing

        X, Y, Z = np.meshgrid(x_1d, y_1d, z_1d, indexing='ij')
        pts_3d = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])

        self.logger.info("[vdW] Computing vdW signed distance field...")
        phi_vdW = self._build_vdw_field(pts_3d, coords, radii)

        mask = (
            (phi_vdW > self.vdw_min_distance) &
            (phi_vdW < self.vdw_shell_thickness)
        )
        shell_points = pts_3d[mask]

        self.logger.info(
            f"[vdW] Shell points found: {len(shell_points):,} "
            f"(threshold=[{self.vdw_min_distance}, {self.vdw_shell_thickness}) Å)"
        )

        if len(shell_points) == 0:
            raise RuntimeError(
                "[vdW] No shell points found! "
                "Try increasing vdw_shell_thickness or decreasing grid_spacing."
            )

        n = self.sample_points
        if len(shell_points) >= n:
            idx = np.random.choice(len(shell_points), size=n, replace=False)
        else:
            self.logger.warning(
                f"[vdW] Only {len(shell_points)} shell points available, "
                f"requested {n}. Sampling with replacement."
            )
            idx = np.random.choice(len(shell_points), size=n, replace=True)

        return shell_points[idx]

    # ================================================================== #
    # Mode 2: SES surface sampling
    # ================================================================== #

    def _generate_ses_points(self, atoms: List[Dict]) -> np.ndarray:
        coords = np.array([a['coord'] for a in atoms])
        radii = np.array([a['radius'] for a in atoms])
        r_probe = self.probe_radius
        
        padding = r_probe + np.max(radii) + 2.0
        min_bounds = np.min(coords, axis=0) - padding
        max_bounds = np.max(coords, axis=0) + padding
        
        nx = int(np.ceil((max_bounds[0] - min_bounds[0]) / self.grid_spacing))
        ny = int(np.ceil((max_bounds[1] - min_bounds[1]) / self.grid_spacing))
        nz = int(np.ceil((max_bounds[2] - min_bounds[2]) / self.grid_spacing))
        
        x_1d = min_bounds[0] + np.arange(nx) * self.grid_spacing
        y_1d = min_bounds[1] + np.arange(ny) * self.grid_spacing
        z_1d = min_bounds[2] + np.arange(nz) * self.grid_spacing
        
        X, Y, Z = np.meshgrid(x_1d, y_1d, z_1d, indexing='ij')
        pts_3d = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
        chunk_size = 500_000
        
        self.logger.info("[SES] Computing vdW signed distance field...")
        phi_vdW = self._build_vdw_field(pts_3d, coords, radii)
        
        self.logger.info("[SES] Computing probe-center SAS field...")
        phi_SAS = np.full(len(pts_3d), np.inf, dtype=np.float32)
        for i in range(len(coords)):
            for start in range(0, len(pts_3d), chunk_size):
                end = min(start + chunk_size, len(pts_3d))
                dist = np.linalg.norm(pts_3d[start:end] - coords[i], axis=1)
                phi_SAS[start:end] = np.minimum(
                    phi_SAS[start:end],
                    dist - (radii[i] + r_probe)
                )
        
        self.logger.info("[SES] Building correct SES signed distance field...")
        valid_probe_centers = pts_3d[phi_SAS >= 0]
        
        if len(valid_probe_centers) == 0:
            raise RuntimeError(
                "[SES] No valid probe centers found! "
                "Try increasing grid spacing or probe radius."
            )
        
        self.logger.info(f"[SES] Found {len(valid_probe_centers):,} valid probe centers")
        
        tree = KDTree(valid_probe_centers)
        dist_to_valid = np.zeros(len(pts_3d), dtype=np.float32)
        for start in range(0, len(pts_3d), chunk_size):
            end = min(start + chunk_size, len(pts_3d))
            d, _ = tree.query(pts_3d[start:end], workers=-1)
            dist_to_valid[start:end] = d
        
        phi_SES = r_probe - dist_to_valid
        phi_SES = np.minimum(phi_SES, phi_vdW)
        
        phi_SES_3D = phi_SES.reshape((nx, ny, nz))
        
        f_min, f_max = float(phi_SES_3D.min()), float(phi_SES_3D.max())
        self.logger.info(f"[SES] phi_SES range: [{f_min:.6f}, {f_max:.6f}] Å")
        
        if f_min >= 0.0 or f_max <= 0.0:
            raise RuntimeError(
                "[SES] SES field does not cross zero! "
                "Check atom radii / grid_spacing / probe_radius."
            )
        
        self.logger.info("[SES] Running Marching Cubes (level=0)...")
        verts, faces, _, _ = measure.marching_cubes(phi_SES_3D, level=0.0)
        
        verts_angstrom = min_bounds + verts * self.grid_spacing
        self._validate_ses_surface(verts_angstrom, coords, radii)
        
        self.logger.info(
            f"[SES] Mesh: {len(verts_angstrom):,} vertices, "
            f"{len(faces):,} faces."
        )
        
        return self._sample_from_mesh(verts_angstrom, faces, self.sample_points)

    def _validate_ses_surface(self, surface_points: np.ndarray, 
                              coords: np.ndarray, radii: np.ndarray):
        min_distances = np.min(
            np.linalg.norm(surface_points[:, None] - coords, axis=2),
            axis=1
        )
        
        nearest_atom_idx = np.argmin(
            np.linalg.norm(surface_points[:, None] - coords, axis=2),
            axis=1
        )
        nearest_radii = radii[nearest_atom_idx]
        
        tolerance = 1e-4
        violations = min_distances < (nearest_radii - tolerance)
        
        if np.any(violations):
            n_violations = np.sum(violations)
            self.logger.error(
                f"[SES] ERROR: {n_violations} surface points are inside vdW spheres! "
                f"Max violation: {np.max(nearest_radii[violations] - min_distances[violations]):.6f} Å"
            )
        else:
            self.logger.info("[SES] Validation passed: All surface points respect vdW constraints")
        
        vdw_distances = min_distances - nearest_radii
        self.logger.info(
            f"[SES] Distance to vdW surface: min={np.min(vdw_distances):.6f}, "
            f"max={np.max(vdw_distances):.6f}, mean={np.mean(vdw_distances):.6f} Å"
        )

    # ================================================================== #
    # Mode 3: EPS surface sampling (continuum dielectric, NumPy rho_mol)
    # ================================================================== #

    def _generate_eps_points(self, atoms: List[Dict]) -> np.ndarray:
        """Extract and sample dielectric surface from rho_mol isosurface."""
        
        # Model constants.
        eps_out = 80.0
        default_eps_in = 4.0
        sigma = 1.4
        gaussian_exponent = self.eps_gaussian_exponent
        surf_den_exponent = 4.0
        target_iso_level = self.eps_target_iso_level

        coords = np.array([a['coord'] for a in atoms])
        radii = np.array([a['radius'] for a in atoms])

        # 1) Build a 3D grid with sufficient padding for density decay.
        padding = sigma * np.max(radii) + 3.0
        min_bounds = np.min(coords, axis=0) - padding
        max_bounds = np.max(coords, axis=0) + padding

        nx = int(np.ceil((max_bounds[0] - min_bounds[0]) / self.grid_spacing))
        ny = int(np.ceil((max_bounds[1] - min_bounds[1]) / self.grid_spacing))
        nz = int(np.ceil((max_bounds[2] - min_bounds[2]) / self.grid_spacing))

        x_1d = min_bounds[0] + np.arange(nx) * self.grid_spacing
        y_1d = min_bounds[1] + np.arange(ny) * self.grid_spacing
        z_1d = min_bounds[2] + np.arange(nz) * self.grid_spacing

        X, Y, Z = np.meshgrid(x_1d, y_1d, z_1d, indexing='ij')
        pts_3d = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])

        self.logger.info(
            f"[EPS] Grid: {nx}×{ny}×{nz} = {nx*ny*nz:,} voxels. "
            f"Computing rho_mol field using NumPy..."
        )

        sigma_vdw_sq = (sigma * radii) ** 2
        
        # Use a conservative chunk size to avoid large memory spikes.
        chunk_size = 50_000 
        rho_mol_full = np.zeros(len(pts_3d), dtype=np.float32)

        # 2) Compute rho_mol chunk by chunk.
        for start in range(0, len(pts_3d), chunk_size):
            end = min(start + chunk_size, len(pts_3d))
            r_chunk = pts_3d[start:end]

            # cdist returns squared distances with shape (N_chunk, N_atoms).
            dist_sq = cdist(r_chunk, coords, metric='sqeuclidean')
            
            # Compute atom-wise rho_i and total rho_mol.
            rho_i = np.exp(-(dist_sq / sigma_vdw_sq) ** gaussian_exponent)
            rho_mol_chunk = 1.0 - np.prod(1.0 - rho_i, axis=1)
            
            rho_mol_full[start:end] = rho_mol_chunk.astype(np.float32)

        rho_mol_3D = rho_mol_full.reshape((nx, ny, nz))
        
        f_min, f_max = float(rho_mol_3D.min()), float(rho_mol_3D.max())
        self.logger.info(f"[EPS] rho_mol range: [{f_min:.6f}, {f_max:.6f}]")

        if f_min >= target_iso_level or f_max <= target_iso_level:
            raise RuntimeError(
                f"[EPS] rho_mol field does not cross {target_iso_level}! "
                "Check system bounding box or atomic density configuration."
            )

        # 3) Run marching cubes to extract the target isosurface.
        self.logger.info(f"[EPS] Running Marching Cubes (level={target_iso_level})...")
        verts, faces, _, _ = measure.marching_cubes(rho_mol_3D, level=target_iso_level)

        # Convert voxel indices into Cartesian coordinates.
        verts_angstrom = min_bounds + verts * self.grid_spacing
        
        self.logger.info(
            f"[EPS] Mesh: {len(verts_angstrom):,} vertices, "
            f"{len(faces):,} faces."
        )

        # 4) Uniformly sample points from mesh faces with area weighting.
        return self._sample_from_mesh(verts_angstrom, faces, self.sample_points)

    # ------------------------------------------------------------------ #
    # Uniform mesh sampling by triangle area
    # ------------------------------------------------------------------ #

    def _sample_from_mesh(
        self,
        verts: np.ndarray,
        faces: np.ndarray,
        num_samples: int
    ) -> np.ndarray:
        if len(faces) == 0:
            self.logger.warning("Empty mesh! Falling back to vertex sampling.")
            idx = np.random.choice(len(verts), size=num_samples, replace=True)
            return verts[idx]

        v0 = verts[faces[:, 0]]
        v1 = verts[faces[:, 1]]
        v2 = verts[faces[:, 2]]

        cross = np.cross(v1 - v0, v2 - v0)
        areas = 0.5 * np.linalg.norm(cross, axis=1)
        total_area = areas.sum()

        if total_area == 0.0:
            self.logger.warning("Zero-area mesh! Falling back to vertex sampling.")
            idx = np.random.choice(len(verts), size=num_samples, replace=True)
            return verts[idx]

        probs = areas / total_area
        face_idx = np.random.choice(len(faces), size=num_samples, p=probs)

        # Generate random points in barycentric coordinates.
        r1 = np.random.rand(num_samples, 1)
        r2 = np.random.rand(num_samples, 1)

        # Fold points back into triangle.
        over = (r1 + r2) > 1.0
        r1[over] = 1.0 - r1[over]
        r2[over] = 1.0 - r2[over]
        r0 = 1.0 - r1 - r2

        return v0[face_idx] * r0 + v1[face_idx] * r1 + v2[face_idx] * r2

    # ------------------------------------------------------------------ #
    # Save output points in angstrom and bohr units
    # ------------------------------------------------------------------ #

    def _save_surface_points(
        self,
        points: np.ndarray,
        ang_file: str,
        bohr_file: str
    ):
        ANG_TO_BOHR = 1.8897261245650618
        points_bohr = points * ANG_TO_BOHR

        with open(ang_file, 'w') as f:
            f.write(f"{len(points)}\n")
            for p in points:
                f.write(f"{p[0]:14.9f} {p[1]:14.9f} {p[2]:14.9f}\n")

        with open(bohr_file, 'w') as f:
            f.write(f"{len(points_bohr)}\n")
            for p in points_bohr:
                f.write(f"{p[0]:14.9f} {p[1]:14.9f} {p[2]:14.9f}\n")


# ------------------------------------------------------------------ #
# Example usage
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # ---- VDW mode ----
    cfg_vdw = {
        'surface_mode': 'vdw',
        'sample_points': 10000,
        'grid_spacing': 0.25,
        'vdw_shell_thickness': 0.5,
        'vdw_min_distance': 0.0,
    }
    # sampler_vdw = PointSampler(cfg_vdw, logger)
    # sampler_vdw.sample("1a2b", "./temp")

    # ---- SES mode ----
    cfg_ses = {
        'surface_mode': 'ses',
        'sample_points': 10000,
        'grid_spacing': 0.25,
        'probe_radius': 1.4,
    }
    # sampler_ses = PointSampler(cfg_ses, logger)
    # sampler_ses.sample("1a2b", "./temp")
    
    # ---- EPS mode ----
    cfg_eps = {
        'surface_mode': 'eps',
        'sample_points': 10000,
        'grid_spacing': 0.25,
    }
    # sampler_eps = PointSampler(cfg_eps, logger)
    # sampler_eps.sample("1a2b", "./temp")