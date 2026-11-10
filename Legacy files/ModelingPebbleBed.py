#!/usr/bin/env python
# coding: utf-8

# In[ ]:

from math import pi
import numpy as np
import matplotlib.pyplot as plt
import openmc
import openmc.model
import openmc.deplete

#Include correct path reference for these files
openmc.config['cross_sections'] = '~/lib80x_hdf5/cross_sections.xml' 
openmc.config['chain_file']     = '~/chain_endfb80_pwr.xml'


# In[ ]:


#Calling on OpenMC to import all of the necessary Isotopes to perform the necessary k-inf analysis

fuel = openmc.Material(name='Fuel')

# 19.75% HALEU UO2
#fuel.set_density('g/cm3', 10.5)
#fuel.add_nuclide('U235', 6.59e-02)
#fuel.add_nuclide('U238', 2.677e-01)
#fuel.add_nuclide('O16',  6.67e-01)

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


# In[ ]:


# Create TRISO universe
#Each value of 'a' represents a different radius filled with a different material
spheres = [openmc.Sphere(r=a*1e-4)
           for a in [215.5, 312.5, 352.5, 387.5]]

cells = [openmc.Cell(fill=fuel, region=-spheres[0]),
         openmc.Cell(fill=buff, region=+spheres[0] & -spheres[1]),
         openmc.Cell(fill=PyC1, region=+spheres[1] & -spheres[2]),
         openmc.Cell(fill=SiC, region=+spheres[2] & -spheres[3]),
         openmc.Cell(fill=PyC2, region=+spheres[3])]
triso_univ = openmc.Universe(cells=cells)


# In[ ]:


outer_radius = 427.5*1e-4   # cm, AGR-reference TRISO outer radius

# Pebble dimensions (HTR-PM / X-energy style)
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


# In[ ]:


# Containing cube around the pebble — reflective BC = infinite pebble lattice
cube_half = pebble_outer_r        # tight cube hugging the pebble (cube side = pebble diameter)
min_x = openmc.XPlane(x0=-cube_half, boundary_type='reflective')
max_x = openmc.XPlane(x0= cube_half, boundary_type='reflective')
min_y = openmc.YPlane(y0=-cube_half, boundary_type='reflective')
max_y = openmc.YPlane(y0= cube_half, boundary_type='reflective')
min_z = openmc.ZPlane(z0=-cube_half, boundary_type='reflective')
max_z = openmc.ZPlane(z0= cube_half, boundary_type='reflective')
cube_region = +min_x & -max_x & +min_y & -max_y & +min_z & -max_z

# Three cells make up the pebble + its surroundings:
#   1. fuel matrix (TRISO lattice fills this below)
#   2. graphite shell around the fuel zone
#   3. helium gap between the pebble and the cube boundary
fuel_matrix_cell = openmc.Cell(name='fuel_matrix', region=-fuel_zone_surf)
shell_cell       = openmc.Cell(name='shell', fill=graphite,
                               region=+fuel_zone_surf & -pebble_outer_surf)
gap_cell         = openmc.Cell(name='gap',   fill=helium,
                               region=+pebble_outer_surf & cube_region)


# In[ ]:


lower_left, upper_right = fuel_matrix_cell.region.bounding_box
shape = (10, 10, 10)
pitch = (upper_right - lower_left) / shape
lattice = openmc.model.create_triso_lattice(
    trisos, lower_left, pitch, shape, graphite)


# In[ ]:


fuel_matrix_cell.fill = lattice


# In[ ]:


univ = openmc.Universe(cells=[fuel_matrix_cell, shell_cell, gap_cell])

geom = openmc.Geometry(univ)
geom.export_to_xml()

mats = list(geom.get_all_materials().values())
openmc.Materials(mats).export_to_xml()

settings = openmc.Settings()
settings.run_mode = 'plot'
settings.export_to_xml()

p = openmc.Plot.from_geometry(geom)
openmc.plot_inline(p)


# In[ ]:


settings = openmc.Settings()
settings.run_mode = 'eigenvalue'
settings.batches = 100          # total batches
settings.inactive = 20          # discard while source converges
settings.particles = 2000       # neutrons per batch

settings.export_to_xml()


# In[ ]:


tallies = openmc.Tallies()

# Energy spectrum in the fuel
energy_filter = openmc.EnergyFilter(np.logspace(-3, 7, 71)) 
fuel_filter   = openmc.MaterialFilter([fuel])
spectrum = openmc.Tally(name='fuel_spectrum')
spectrum.filters = [energy_filter, fuel_filter]
spectrum.scores  = ['flux']
tallies.append(spectrum)

# Fission / absorption rates in the fuel
rxn = openmc.Tally(name='fuel_rxn_u235')
rxn.filters = [fuel_filter]
rxn.nuclides = ['U235']
rxn.scores  = ['fission', 'absorption', '(n,gamma)']
tallies.append(rxn)

tallies.export_to_xml()


# In[ ]:


openmc.run() #Starting K-inf values 


# In[ ]:


sp  = openmc.StatePoint('statepoint.100.h5')
rxn = sp.get_tally(name='fuel_rxn_u235')        # ← this rxn has .mean and .std_dev

for score, mean, sd in zip(rxn.scores, rxn.mean.flatten(), rxn.std_dev.flatten()):
    print(f"{score:>12s} : {mean:.4e}  +/- {sd:.2e}")


# In[ ]:


fission, absorption, ngamma = rxn.mean.flatten()
alpha = ngamma / fission
P_f   = fission / absorption
nu    = 2.43                          # U-235 thermal, approximate
eta   = nu * P_f

print(f"alpha (capture/fission) = {alpha:.3f}    (ideal ~0.17 for U-235 thermal)")
print(f"P_fission              = {P_f:.3f}    (ideal ~0.85)")
print(f"eta                    = {eta:.3f}    (ideal ~2.07)")


# In[ ]:


spec = sp.get_tally(name='fuel_spectrum')
flux = spec.mean.flatten()

energy_bins = np.logspace(-3, 7, 71)            
midpoints   = 0.5 * (energy_bins[1:] + energy_bins[:-1])
plt.loglog(midpoints, flux / np.diff(energy_bins))
plt.xlabel('Energy [eV]'); plt.ylabel(r'$\phi(E)$ [n/cm²/eV/src]')


# In[ ]:




