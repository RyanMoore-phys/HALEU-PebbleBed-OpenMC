
from math import pi
import numpy as np
import matplotlib.pyplot as plt
import openmc
import openmc.model
import openmc.deplete

# Include correct path reference for these files
openmc.config['cross_sections'] = '~/lib80x_hdf5/cross_sections.xml'
openmc.config['chain_file']     = '~/chain_endfb80_pwr.xml'

fuel = openmc.Material(name='Fuel')

# 19.75% HALEU UCO
fuel.set_density('g/cm3', 10.9)
fuel.add_nuclide('U235', 0.0659)
fuel.add_nuclide('U238', 0.2677)
fuel.add_nuclide('O16',  0.534)     # ~80% UO2
fuel.add_nuclide('C12',  0.131)     # ~20% UC2
fuel.add_nuclide('C13',  0.0014)

buff = openmc.Material(name='Buffer')
buff.set_density('g/cm3', 1.05)
buff.add_element('C', 1.0)
buff.add_s_alpha_beta('c_Graphite')

PyC1 = openmc.Material(name='PyC1')
PyC1.set_density('g/cm3', 1.9)
PyC1.add_element('C', 1.0)
PyC1.add_s_alpha_beta('c_Graphite')

PyC2 = openmc.Material(name='PyC2')
PyC2.set_density('g/cm3', 1.87)
PyC2.add_element('C', 1.0)
PyC2.add_s_alpha_beta('c_Graphite')

SiC = openmc.Material(name='SiC')
SiC.set_density('g/cm3', 3.2)
SiC.add_element('C', 0.5)
SiC.add_element('Si', 0.5)

graphite = openmc.Material(name='Matrix')
graphite.set_density('g/cm3', 1.74)
graphite.add_element('C', 1.0)
graphite.add_s_alpha_beta('c_Graphite')

# Helium coolant in the gap between pebbles
helium = openmc.Material(name='Helium')
helium.set_density('g/cm3', 0.0001785)
helium.add_element('He', 1.0)

# Create TRISO universe
spheres = [openmc.Sphere(r=a*1e-4)
           for a in [215.5, 312.5, 352.5, 387.5]]
cells = [openmc.Cell(fill=fuel, region=-spheres[0]),
         openmc.Cell(fill=buff, region=+spheres[0] & -spheres[1]),
         openmc.Cell(fill=PyC1, region=+spheres[1] & -spheres[2]),
         openmc.Cell(fill=SiC, region=+spheres[2] & -spheres[3]),
         openmc.Cell(fill=PyC2, region=+spheres[3])]
triso_univ = openmc.Universe(cells=cells)

outer_radius = 427.5*1e-4   # cm, AGR-reference TRISO outer radius

# ===== Pebble dimensions (HTR-PM / X-energy style) =====
pebble_outer_r = 3.0    # 3.0 cm pebble outer radius (6 cm diameter)
fuel_zone_r    = 2.5    # 2.5 cm fuel-zone radius (0.5 cm graphite shell)

pebble_outer_surf = openmc.Sphere(r=pebble_outer_r)
fuel_zone_surf    = openmc.Sphere(r=fuel_zone_r)

# Pack TRISOs into the spherical fuel zone (not a cube!)
centers = openmc.model.pack_spheres(
    radius=outer_radius,
    region=-fuel_zone_surf,
    pf=0.09,                # HTR-PM uses ~9% packing in the fuel zone
)

trisos = [openmc.model.TRISO(outer_radius, triso_univ, c) for c in centers]

# Containing cube around the pebble - reflective BC = infinite pebble lattice
cube_half = pebble_outer_r        # tight cube hugging the pebble
min_x = openmc.XPlane(x0=-cube_half, boundary_type='reflective')
max_x = openmc.XPlane(x0= cube_half, boundary_type='reflective')
min_y = openmc.YPlane(y0=-cube_half, boundary_type='reflective')
max_y = openmc.YPlane(y0= cube_half, boundary_type='reflective')
min_z = openmc.ZPlane(z0=-cube_half, boundary_type='reflective')
max_z = openmc.ZPlane(z0= cube_half, boundary_type='reflective')
cube_region = +min_x & -max_x & +min_y & -max_y & +min_z & -max_z

fuel_matrix_cell = openmc.Cell(name='fuel_matrix', region=-fuel_zone_surf)
shell_cell       = openmc.Cell(name='shell', fill=graphite,
                               region=+fuel_zone_surf & -pebble_outer_surf)
gap_cell         = openmc.Cell(name='gap',   fill=helium,
                               region=+pebble_outer_surf & cube_region)

lower_left, upper_right = fuel_matrix_cell.region.bounding_box
shape = (10, 10, 10)
pitch = (upper_right - lower_left) / shape
lattice = openmc.model.create_triso_lattice(
    trisos, lower_left, pitch, shape, graphite)
fuel_matrix_cell.fill = lattice

univ = openmc.Universe(cells=[fuel_matrix_cell, shell_cell, gap_cell])
geom = openmc.Geometry(univ)

import gc, os
gc.collect()
for f in ['summary.h5', 'statepoint.100.h5', 'depletion_results.h5']:
    if os.path.exists(f):
        os.remove(f); print(f"removed {f}")

# --- (1) Tell OpenMC the total fuel kernel volume (required for burnup units) ---
kernel_radius_cm = 215.5e-4
fuel.volume = len(trisos) * (4/3) * np.pi * kernel_radius_cm**3
print(f"Total fuel volume: {fuel.volume:.4f} cm^3 across {len(trisos)} kernels")

# --- (2) Lighter settings just for depletion (per-step expensive) ---
dep_settings = openmc.Settings()
dep_settings.run_mode  = 'eigenvalue'
dep_settings.batches   = 50
dep_settings.inactive  = 10
dep_settings.particles = 2000

# --- (3) Build the openmc.Model wrapper ---
mats = list(geom.get_all_materials().values())
model = openmc.Model(geometry=geom,
                     settings=dep_settings,
                     materials=openmc.Materials(mats))

# --- (4) Coupled operator (couples transport + Bateman depletion solver) ---
operator = openmc.deplete.CoupledOperator(model)

# --- (5) Time steps and per-pebble power ---
# HTR-PM nominal: 250 MWth / 420,000 pebbles ~= 595 W/pebble
power_per_pebble_W = 595.0

# START SMALL to verify everything works (~5 minutes total):
time_steps_short = [30, 30, 30]            # 90 EFPD in 3 steps

# FULL CYCLE (uncomment when short test passes; ~30-60 minutes):
#time_steps_full = [30] * 36              # 1080 EFPD in 36 steps (~3 years)

time_steps = time_steps_short             # change to time_steps_full for the real run

# --- (6) Run depletion ---
integrator = openmc.deplete.PredictorIntegrator(
    operator,
    time_steps,
    power=power_per_pebble_W,
    timestep_units='d',
)
integrator.integrate()

# --- (7) Read depletion results and plot burnup curve ---
results = openmc.deplete.Results('depletion_results.h5')

time_s, k_arr = results.get_keff()
time_efpd = time_s / 86400.0
k_mean = k_arr[:, 0]
k_std  = k_arr[:, 1]

# Burnup in MWd/kgU (heavy-metal mass basis)
atom_fracs = {'U235': 0.0659, 'U238': 0.2677, 'O16': 0.534, 'C12': 0.131, 'C13': 0.0014}
A = {'U235': 235, 'U238': 238, 'O16': 16, 'C12': 12, 'C13': 13}
mass_total = sum(atom_fracs[k]*A[k] for k in atom_fracs)
mass_U     = atom_fracs['U235']*235 + atom_fracs['U238']*238
U_mass_frac = mass_U / mass_total

heavy_metal_kg = fuel.volume * 10.9 * U_mass_frac / 1000.0   # kg of U
burnup_MWd_kgU = (power_per_pebble_W/1e6) * time_efpd / heavy_metal_kg

fig, axes = plt.subplots(1, 2, figsize=(12, 4))

axes[0].errorbar(time_efpd, k_mean, yerr=k_std, marker='o', capsize=3)
axes[0].axhline(1.0, ls='--', color='gray', label='criticality')
axes[0].set_xlabel('Time [EFPD]'); axes[0].set_ylabel('k$_\\infty$')
axes[0].set_title('Pebble k$_\\infty$ vs. burn time')
axes[0].legend(); axes[0].grid(alpha=0.3)

axes[1].errorbar(burnup_MWd_kgU, k_mean, yerr=k_std, marker='o', capsize=3)
axes[1].axhline(1.0, ls='--', color='gray')
axes[1].set_xlabel('Burnup [MWd/kgU]'); axes[1].set_ylabel('k$_\\infty$')
axes[1].set_title('Pebble k$_\\infty$ vs. burnup')
axes[1].grid(alpha=0.3)

plt.tight_layout()
plt.savefig('burnup_curve.png', dpi=150, bbox_inches='tight')
plt.show()

print(f"\nFinal k = {k_mean[-1]:.4f} +/- {k_std[-1]:.4f}")
print(f"Final burnup = {burnup_MWd_kgU[-1]:.2f} MWd/kgU")

# --- (8) Track key isotope inventories over the burn ---
_, u235  = results.get_atoms(fuel, 'U235')
_, u238  = results.get_atoms(fuel, 'U238')
_, pu239 = results.get_atoms(fuel, 'Pu239')
_, xe135 = results.get_atoms(fuel, 'Xe135')

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(time_efpd, u235  / u235[0],  marker='o', label='U-235 (normalized)')
ax.plot(time_efpd, pu239 / u235[0],  marker='s', label='Pu-239 / U-235(0)')
ax.plot(time_efpd, xe135 / u235[0],  marker='^', label='Xe-135 / U-235(0)')
ax.set_xlabel('Time [EFPD]'); ax.set_ylabel('Atoms (relative to initial U-235)')
ax.set_title('Key isotope inventories during burnup')
ax.set_yscale('log')
ax.legend(); ax.grid(alpha=0.3, which='both')
plt.tight_layout()
plt.savefig('isotope_inventory.png', dpi=150, bbox_inches='tight')
plt.show()
