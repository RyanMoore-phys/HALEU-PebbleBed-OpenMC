#!/usr/bin/env python
# coding: utf-8

# In[17]:


import os
from math import pi
import numpy as np
import matplotlib.pyplot as plt
import openmc
import openmc.model


#Include correct path reference for these files
openmc.config['cross_sections'] = '/Users/ryanmoore/Desktop/Nuclear/lib80x_hdf5/cross_sections.xml' 
openmc.config['chain_file']     = '/Users/ryanmoore/Desktop/Nuclear/chain_endfb80_pwr.xml'



# In[18]:


#Kelvin
#These are the temperatures we will sweep over based on
#the cross-section data temperatures
temps = [293, 450, 600, 750, 900, 1050, 1200] 
k_inf_results = []
k_inf_errors = []

#Packing TRISO centers once, ensure consistant geometry
_fuel_zone_static = openmc.Sphere(r=2.5)
_outer_r_static   = 427.5e-4
centers = openmc.model.pack_spheres(
    radius=_outer_r_static,
    region=-_fuel_zone_static,
    pf=0.09,
)

#For every temperature, perform a k-inf analysis
for T in temps:
    #Materials
    fuel = openmc.Material(name='Fuel')
    fuel.set_density('g/cm3', 10.9)
    fuel.add_nuclide('U235', 0.0659)
    fuel.add_nuclide('U238', 0.2677)
    fuel.add_nuclide('O16',  0.534)     # ~80% UO2
    fuel.add_nuclide('C12',  0.131)     # ~20% UC2
    fuel.add_nuclide('C13',  0.0014)
    fuel.temperature = T #Sweep

    buff = openmc.Material(name='Buffer')
    buff.set_density('g/cm3', 1.05)
    buff.add_element('C', 1.0)
    buff.add_s_alpha_beta('c_Graphite')
    buff.temperature = T

    PyC1 = openmc.Material(name='PyC1')
    PyC1.set_density('g/cm3', 1.9)
    PyC1.add_element('C', 1.0)
    PyC1.add_s_alpha_beta('c_Graphite')
    PyC1.temperature = T

    PyC2 = openmc.Material(name='PyC2')
    PyC2.set_density('g/cm3', 1.87)
    PyC2.add_element('C', 1.0)
    PyC2.add_s_alpha_beta('c_Graphite')
    PyC2.temperature = T

    SiC = openmc.Material(name='SiC')
    SiC.set_density('g/cm3', 3.2)
    SiC.add_element('C', 0.5)
    SiC.add_element('Si', 0.5)
    SiC.temperature = T

    graphite = openmc.Material(name='Matrix')
    graphite.set_density('g/cm3', 1.74)
    graphite.add_element('C', 1.0)
    graphite.add_s_alpha_beta('c_Graphite')
    graphite.temperature = T

    # Helium coolant in the gap between pebbles
    helium = openmc.Material(name='Helium')
    helium.set_density('g/cm3', 0.0001785)
    helium.add_element('He', 1.0)
    helium.temperature = T

    #TRISO Universe
    spheres = [openmc.Sphere(r=a*1e-4)
           for a in [215.5, 312.5, 352.5, 387.5, 427.5]]

    cells = [openmc.Cell(fill=fuel, region=-spheres[0]),
         openmc.Cell(fill=buff, region=+spheres[0] & -spheres[1]),
         openmc.Cell(fill=PyC1, region=+spheres[1] & -spheres[2]),
         openmc.Cell(fill=SiC,  region=+spheres[2] & -spheres[3]),
         openmc.Cell(fill=PyC2, region=+spheres[3] & -spheres[4])]
    triso_univ = openmc.Universe(cells=cells)

    #Pebble Geometry
    outer_radius    = spheres[4].r
    pebble_outer_r  = 3.0
    fuel_zone_r     = 2.5
    pebble_outer_surf = openmc.Sphere(r=pebble_outer_r)
    fuel_zone_surf    = openmc.Sphere(r=fuel_zone_r)
    
    trisos = [openmc.model.TRISO(outer_radius, triso_univ, c) for c in centers]

    #Cells
    cube_half = pebble_outer_r
    min_x = openmc.XPlane(x0=-cube_half, boundary_type='reflective')
    max_x = openmc.XPlane(x0= cube_half, boundary_type='reflective')
    min_y = openmc.YPlane(y0=-cube_half, boundary_type='reflective')
    max_y = openmc.YPlane(y0= cube_half, boundary_type='reflective')
    min_z = openmc.ZPlane(z0=-cube_half, boundary_type='reflective')
    max_z = openmc.ZPlane(z0= cube_half, boundary_type='reflective')
    cube_region = +min_x & -max_x & +min_y & -max_y & +min_z & -max_z

    fuel_matrix_cell = openmc.Cell(name='fuel_matrix', region=-fuel_zone_surf)
    shell_cell       = openmc.Cell(name='shell', fill=graphite, region=+fuel_zone_surf & -pebble_outer_surf)
    gap_cell         = openmc.Cell(name='gap', fill=helium, region=+pebble_outer_surf & cube_region)

    lower_left, upper_right = fuel_matrix_cell.region.bounding_box
    shape   = (10, 10, 10)
    pitch   = (upper_right - lower_left) / shape
    lattice = openmc.model.create_triso_lattice(trisos, lower_left, pitch, shape, graphite)
    fuel_matrix_cell.fill = lattice

    univ = openmc.Universe(cells=[fuel_matrix_cell, shell_cell, gap_cell])
    geom = openmc.Geometry(univ)

    #Settings

    settings = openmc.Settings()
    settings.batches = 100
    settings.inactive = 20
    settings.particles = 2000
    settings.temperature = {'method': 'interpolation','range': [293, 1200]}

    #Run
    run_dir = f'run_T{int(T)}K'
    os.makedirs(run_dir, exist_ok=True)
    
    materials = openmc.Materials([fuel, buff, PyC1, PyC2, SiC, graphite, helium])
    model = openmc.Model(geom, materials, settings)
    sp_file = model.run(cwd=run_dir)

    #Determining K

    with openmc.StatePoint(sp_file) as sp:
        k_inf_results.append(sp.keff.nominal_value)
        k_inf_errors.append(sp.keff.std_dev)

print(list(zip(temps, k_inf_results)))



# In[19]:


import os
#Include correct path
#Check if location exists/Makes a folder where specified for figures
os.makedirs('Users/ryanmoore/Desktop/Nuclear/figures', exist_ok=True)

# In[20]:


import numpy as np
import matplotlib.pyplot as plt

#Reactivity conversion
def reactivity_pcm(k):
    return (k - 1) / k * 1e5
rho = [reactivity_pcm(k) for k in k_inf_results]


#Doppler coefficient (pcm/K) between each adjacent pair
alpha_D = []
alpha_D_temps = []
for i in range(1, len(temps)):
    delta_rho = rho[i] - rho[i-1]
    delta_T   = temps[i] - temps[i-1]
    alpha_D.append(delta_rho / delta_T)
    alpha_D_temps.append(0.5 * (temps[i] + temps[i-1]))  # midpoint temp

print(len(temps), len(rho))
#Linear fit to rho vs T 
coeffs = np.polyfit(temps, rho, 1)
fit_line = np.poly1d(coeffs)
print(f"Integrated Doppler coefficient (linear fit): {coeffs[0]:.2f} pcm/K")


# Figure 1 — k∞ vs Fuel Temperature

fig, ax = plt.subplots(figsize=(8, 5))
ax.errorbar(temps, k_inf_results, yerr=k_inf_errors,
            fmt='o-', color='steelblue', capsize=4,
            linewidth=1.8, markersize=6, label='OpenMC (this work)')
ax.axhline(1.0, color='gray', linestyle='--', linewidth=1, label='Critical (k=1)')
ax.set_xlabel('Fuel Temperature [K]', fontsize=13)
ax.set_ylabel(r'$k_{\infty}$', fontsize=13)
ax.set_title('19.75% HALEU UCO Pebble — $k_{\infty}$ vs Fuel Temperature', fontsize=13)
ax.legend(fontsize=11)
ax.grid(True, alpha=0.3)
plt.tight_layout()
#Make a figures folder on your computer
#Include correct path reference for .savefig
plt.savefig('/Users/ryanmoore/Desktop/Nuclear/figures/kinf_vs_temperature.png', dpi=150)
plt.show()


# Figure 2 — Reactivity vs Temperature with Doppler fit

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(temps, rho, 'o', color='blue', markersize=7, label='OpenMC (this work)')
ax.plot(temps, fit_line(temps), '--', color='tomato', linewidth=1.8,
        label=f'Linear fit: {coeffs[0]:.2f} pcm/K')
ax.set_xlabel('Fuel Temperature [K]', fontsize=13)
ax.set_ylabel(r'Reactivity $\rho$ [pcm]', fontsize=13)
ax.set_title('19.75% HALEU UCO Pebble — Doppler Reactivity Feedback', fontsize=13)
ax.legend(fontsize=11)
ax.grid(True, alpha=0.3)
plt.tight_layout()
#Include correct path reference for .savefig
plt.savefig('/Users/ryanmoore/Desktop/Nuclear/figures/doppler_reactivity.png', dpi=150)
plt.show()


# Figure 3 — Point-to-point Doppler coefficient

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(alpha_D_temps, alpha_D, 's-', color='orange',
        linewidth=1.8, markersize=7)
ax.axhline(0, color='gray', linestyle='--', linewidth=1)
ax.set_xlabel('Temperature [K]', fontsize=13)
ax.set_ylabel(r'$\alpha_D$ [pcm/K]', fontsize=13)
ax.set_title('19.75% HALEU UCO Pebble — Doppler Coefficient vs Temperature', fontsize=13)
ax.grid(True, alpha=0.3)
plt.tight_layout()
#Include correct path reference for .savefig
plt.savefig('/Users/ryanmoore/Desktop/Nuclear/figures/doppler_coefficient.png', dpi=150)
plt.show()

#Print summary table
print("\n--- Results Summary ---")
print(f"{'Temp (K)':<12} {'k_inf':<10} {'rho (pcm)':<12} {'sigma':<10}")
for i, T in enumerate(temps):
    print(f"{T:<12} {k_inf_results[i]:<10.5f} {rho[i]:<12.1f} {k_inf_errors[i]:<10.5f}")

# In[ ]:



