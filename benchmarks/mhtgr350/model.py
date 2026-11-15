"""Explicit-TRISO supercell for the no-poison MHTGR lattice exercises.

One reflective axial slice represents the axially uniform lattice exercise,
not the finite 79.3 cm reactor element. Slice/packing sensitivity must be checked.
"""
import hashlib
import json
import math
import warnings
from pathlib import Path

import numpy as np
import openmc
import openmc.model

from .layout import audit_layout, pin_map

HERE = Path(__file__).parent


def material(name, densities, temperature):
    m = openmc.Material(name=name)
    for nuclide, density in densities.items():
        if nuclide in ('C_nat', 'C_graph'):
            m.add_nuclide('C12', density*.989)
            m.add_nuclide('C13', density*.011)
        else:
            m.add_nuclide(nuclide, density)
    m.set_density('sum')
    m.temperature = temperature
    if 'C_graph' in densities:
        m.add_s_alpha_beta('c_Graphite')
    return m


def build(case):
    spec = json.loads((HERE/'specification.json').read_text())
    audit = audit_layout(spec)
    d, temperature, height = spec['dimensions'], case['temperature_K'], case['slice_height_cm']
    if case['exercise'] not in ('1a','2a') or height < 0.5:
        raise ValueError('Only no-poison exercises and slices >= 0.5 cm are supported')
    materials = {name:material(name, values, temperature)
                 for name,values in spec['number_densities_atom_b_cm'].items() if name!='kernel'}
    radii = d['triso_radii_cm']
    compact = (-openmc.ZCylinder(r=d['compact_radius_cm']) &
               +openmc.ZPlane(z0=-height/2) & -openmc.ZPlane(z0=height/2))
    centers = openmc.model.pack_spheres(radii[-1], compact, pf=d['packing_fraction'],
                                      seed=case['packing_seed'])
    # Verify containment and pair separation, independently of the packing generator.
    from scipy.spatial import cKDTree
    centers = np.asarray(centers)
    if len(centers)<2:
        raise ValueError('TRISO packing failed')
    nearest = cKDTree(centers).query(centers,k=2)[0][:,1].min()
    if nearest < 2*radii[-1] - 1e-10:
        raise ValueError('Overlapping TRISO particles')
    if np.max(np.linalg.norm(centers[:,:2],axis=1)) + radii[-1] > d['compact_radius_cm'] + 1e-10:
        raise ValueError('TRISO crosses compact side')
    if np.max(np.abs(centers[:,2])) + radii[-1] > height/2 + 1e-10:
        raise ValueError('TRISO crosses axial slice boundary')
    pf = len(centers)*4*math.pi*radii[-1]**3/3/(math.pi*d['compact_radius_cm']**2*height)
    if abs(pf/d['packing_fraction']-1)>.001:
        raise ValueError('Realized packing fraction differs by more than 0.1%')
    # Packing can put a sphere tangent to a compact end plane. An exactly equal
    # tracking-grid boundary can classify its bounding box into an outside bin
    # through floating-point rounding. Pad only the acceleration grid; the
    # physical cylinder and axial surfaces remain unchanged.
    lower, upper = compact.bounding_box
    bounds = (np.asarray(lower)-1e-8, np.asarray(upper)+1e-8)
    shape = np.maximum(1,np.ceil((bounds[1]-bounds[0])/(6*radii[-1])).astype(int))
    local_surfaces = [openmc.Sphere(r=r) for r in radii[:-1]]
    layer_regions = openmc.model.subdivide(local_surfaces)
    half = d['block_flat_to_flat_cm']/2
    inner = openmc.model.HexagonalPrism(edge_length=2*half/math.sqrt(3),orientation='x')
    outer = openmc.model.HexagonalPrism(edge_length=d['supercell_flat_to_flat_cm']/math.sqrt(3),
                                        orientation='x',boundary_type='reflective')
    axial = (+openmc.ZPlane(z0=-height/2,boundary_type='reflective') &
             -openmc.ZPlane(z0=height/2,boundary_type='reflective'))
    # Figure III-1: three upper reflector neighbours, three lower burned neighbours.
    # The interfaces continue diagonally through the outer partial blocks.
    corner_x = 2*d['block_flat_to_flat_cm']/math.sqrt(3)
    left, right = openmc.XPlane(x0=-corner_x), openmc.XPlane(x0=corner_x)
    north = openmc.YPlane(y0=0)
    sl = openmc.Plane(a=-math.sqrt(3), b=1, d=math.sqrt(3)*corner_x)
    sr = openmc.Plane(a=-math.sqrt(3), b=1, d=-math.sqrt(3)*corner_x)
    reflector_region = (-left & +sl) | (+left & -right & +north) | (+right & +sr)
    cells = [openmc.Cell(fill=materials['reflector'],region=-outer & +inner & axial & reflector_region),
             openmc.Cell(fill=materials['burned'],region=-outer & +inner & axial & ~reflector_region)]
    graphite_region = -inner & axial
    fuels, sources, pin_metadata, fuel_cells = [], [], [], []
    for p in pin_map(d['pitch_cm']):
        if p['kind'] in ('central_graphite','corner_graphite'):
            continue  # No hole/gap remains at the replaced poison positions.
        hole_r = d['large_coolant_radius_cm'] if p['kind']=='large_coolant' else d['gap_radius_cm']
        hole = openmc.ZCylinder(x0=p['x'],y0=p['y'],r=hole_r)
        graphite_region &= +hole
        if p['kind'] != 'fuel':
            cells.append(openmc.Cell(fill=materials['helium'],region=-hole & axial))
            continue
        fuel = material(f'fuel pin {p["pin"]}',spec['number_densities_atom_b_cm']['kernel'],temperature)
        fuel.depletable = True
        fuel.volume = len(centers)*4*math.pi*radii[0]**3/3
        layers = [fuel]+[materials[k] for k in ('buffer','ipyc','sic','opyc')]
        triso = openmc.Universe(cells=[openmc.Cell(fill=m,region=r) for m,r in zip(layers,layer_regions)])
        particles = [openmc.model.TRISO(radii[-1],triso,center) for center in centers]
        with warnings.catch_warnings():
            warnings.filterwarnings('error', message='TRISO particle is partially or completely.*')
            packed = openmc.model.create_triso_lattice(particles,bounds[0],(bounds[1]-bounds[0])/shape,
                                                      tuple(shape),materials['matrix'])
        local_cylinder = openmc.ZCylinder(r=d['compact_radius_cm'])
        local = openmc.Universe(cells=[openmc.Cell(fill=packed,region=-local_cylinder),
                                       openmc.Cell(fill=materials['helium'],region=+local_cylinder)])
        cell = openmc.Cell(name=f'compact {p["pin"]}',fill=local,region=-hole & axial)
        cell.translation = (p['x'],p['y'],0)
        cells.append(cell)
        fuel_cells.append(cell)
        fuels.append(fuel)
        sources.append(openmc.IndependentSource(space=openmc.stats.Point(
            centers[0]+np.array([p['x'],p['y'],0.]))))
        pin_metadata.append(dict(pin=p['pin'],material_id=fuel.id,volume_cm3=fuel.volume,x=p['x'],y=p['y']))
    cells.append(openmc.Cell(fill=materials['graphite'],region=graphite_region))
    geometry = openmc.Geometry(cells)
    settings = openmc.Settings()
    # Each compact already has a distinct material; no distribcell/instance
    # tallies or distributed materials are used. Avoid offset tables for every
    # repeated TRISO layer, which exhausted the 28 GiB container during plotting.
    settings.material_cell_offsets = False
    # The explicit TRISO geometry creates a very large optional HDF5 geometry
    # summary. Serial metadata writes to EFS stalled the geometry check for >30
    # minutes. XML/audit/plots retain geometry provenance; statepoints and
    # depletion_results.h5 are still written and used by the comparison code.
    settings.output = {'summary': False}
    settings.particles, settings.batches = case['particles'],case['batches']
    settings.inactive, settings.seed = case['inactive'],case['transport_seed']
    settings.temperature = {'default':temperature,'method':'interpolation',
                            'tolerance':case['temperature_tolerance_K']}
    settings.source = sources
    settings.max_lost_particles = 1
    mesh = openmc.RegularMesh()
    mesh.lower_left,mesh.upper_right = (-21,-18,-height/2),(21,18,height/2)
    mesh.dimension = (20,20,1)
    settings.entropy_mesh = mesh
    tally = openmc.Tally(name='compact fission rates')
    tally.filters = [openmc.CellFilter(fuel_cells)]
    tally.scores = ['fission']
    model = openmc.Model(geometry=geometry,materials=openmc.Materials(geometry.get_all_materials().values()),
                        settings=settings,tallies=openmc.Tallies([tally]))
    # Independent point-location check of translated fuel universes on every pin.
    for source,fuel in zip(sources,fuels):
        found = geometry.find(tuple(source.space.xyz))
        if not found or getattr(found[-1],'fill',None) is not fuel:
            raise ValueError(f'Source is not in the expected fuel: {fuel.name}')
    audit.update(kernels_per_compact=len(centers),realized_packing_fraction=pf,
                 minimum_TRISO_separation_cm=float(nearest),source_locations_checked=len(sources),
                 packing_sha256=hashlib.sha256(centers.tobytes()).hexdigest(),
                 tracking_grid_padding_cm=1e-8,material_cell_offsets=False,
                 slice_height_cm=height,geometry_debug='not_run')
    return model, fuels, pin_metadata, audit
