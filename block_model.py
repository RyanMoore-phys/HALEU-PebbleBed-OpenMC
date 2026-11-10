"""Finite graphite prism with one hex lattice and one shared kernel inventory."""
from math import pi, sqrt

import numpy as np
import openmc
import openmc.model


def particle():
    # Material atom fractions and coating dimensions from PebbleBedDepletion.py.
    fuel = openmc.Material(name="UCO kernel")
    fuel.set_density("g/cm3", 10.9)
    for name, fraction in {"U235": .0659, "U238": .2677, "O16": .534,
                           "C12": .131, "C13": .0014}.items():
        fuel.add_nuclide(name, fraction)
    fuel.depletable = True

    def carbon(name, density):
        material = openmc.Material(name=name)
        material.set_density("g/cm3", density)
        material.add_element("C", 1.0)
        material.add_s_alpha_beta("c_Graphite")
        return material

    sic = openmc.Material(name="Silicon carbide")
    sic.set_density("g/cm3", 3.2)
    sic.add_element("Si", .5)
    sic.add_element("C", .5)
    layers = [fuel, carbon("Buffer", 1.05), carbon("Inner PyC", 1.9),
              sic, carbon("Outer PyC", 1.87)]
    radii = np.array([215.5, 312.5, 352.5, 387.5, 427.5]) * 1e-4
    regions = openmc.model.subdivide([openmc.Sphere(r=r) for r in radii[:-1]])
    universe = openmc.Universe(cells=[openmc.Cell(fill=layer, region=region)
                                      for layer, region in zip(layers, regions)])
    return universe, fuel, carbon("Graphite", 1.74), radii


def build_model(g, case):
    edge, height = g["block_edge_cm"], g["block_height_cm"]
    radius, length = g["compact_radius_cm"], g["compact_height_cm"]
    pitch, rings = g["pitch_cm"], g["rings_outer_to_inner"]
    if not rings or rings[-1] != "F":
        raise ValueError("The central source site must contain fuel (F)")
    for i, ring in enumerate(reversed(rings)):
        if len(ring) != max(1, 6*i) or set(ring) - {"F", "G"}:
            raise ValueError(f"Invalid ring {i}: {ring}")
    if not (0 < 2*radius < pitch and 0 < length < height
            and (len(rings)-1)*pitch + radius < sqrt(3)*edge/2):
        raise ValueError("Compacts must fit within their sites and the block")
    triso, fuel, graphite, radii = particle()
    if not (0 < g["packing_fraction"] < 0.64 and radii[-1] < min(radius, length/2)):
        raise ValueError("Invalid compact packing inputs")
    compact = (-openmc.ZCylinder(r=radius) & +openmc.ZPlane(z0=-length/2)
               & -openmc.ZPlane(z0=length/2))
    centers = openmc.model.pack_spheres(radii[-1], compact, pf=g["packing_fraction"],
                                        seed=g["packing_seed"])
    if not len(centers):
        raise ValueError("Compact contains no fuel")
    particles = [openmc.model.TRISO(radii[-1], triso, c) for c in centers]
    lower, upper = compact.bounding_box
    shape = np.maximum(1, np.ceil((upper-lower)/(6*radii[-1])).astype(int))
    packed = openmc.model.create_triso_lattice(particles, lower, (upper-lower)/shape,
                                               tuple(shape), graphite)
    solid = openmc.Universe(cells=[openmc.Cell(fill=graphite)])
    site = openmc.Universe(cells=[openmc.Cell(fill=packed, region=compact),
                                  openmc.Cell(fill=graphite, region=~compact)])
    lattice = openmc.HexLattice()
    lattice.center, lattice.pitch, lattice.outer = (0., 0.), (pitch,), solid
    lattice.universes = [[site if mark == "F" else solid for mark in ring] for ring in rings]
    boundary = openmc.model.HexagonalPrism(edge_length=edge, boundary_type="vacuum")
    block = (-boundary & +openmc.ZPlane(z0=-height/2, boundary_type="vacuum")
             & -openmc.ZPlane(z0=height/2, boundary_type="vacuum"))
    geometry = openmc.Geometry([openmc.Cell(fill=lattice, region=block)])
    count = sum(ring.count("F") for ring in rings)
    fuel.volume = count * len(centers) * 4*pi*radii[0]**3/3
    settings = openmc.Settings()
    settings.batches, settings.inactive = case["batches"], case["inactive"]
    settings.particles, settings.seed = case["particles"], case["transport_seed"]
    settings.temperature = {"default": g["temperature_K"], "method": "interpolation"}
    settings.source = openmc.IndependentSource(space=openmc.stats.Point(centers[0]))
    model = openmc.Model(geometry=geometry, settings=settings,
                         materials=openmc.Materials(geometry.get_all_materials().values()))
    return model, fuel, {"compact_count": count, "kernels_per_compact": len(centers)}
