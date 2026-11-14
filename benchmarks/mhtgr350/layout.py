"""Analytic pin map; no OpenMC dependency or transport calculations.

Figure III-3, 2015 specification: rows north to south, west to east.
Number fuel and corner graphite positions, skipping coolant/central graphite.
"""
import math
from collections import Counter


def validate_case(case):
    expected = {'1a':293.6, '2a':1200.0}
    if case['exercise'] not in expected or case['temperature_K'] != expected[case['exercise']]:
        raise ValueError('Temperature does not match the selected benchmark exercise')
    if case['mode']=='depletion' and case['exercise']!='2a':
        raise ValueError('Depletion requires exercise 2a')
    if case['mode'] not in ('geometry','transport','depletion'):
        raise ValueError('Unsupported calculation mode')
    if case['mode']=='transport' and case['exercise']!='1a':
        raise ValueError('Standalone transport requires exercise 1a')
    if not (0<=case['inactive']<case['batches'] and case['particles']>0):
        raise ValueError('Invalid Monte Carlo settings')
    if not (.5<=case['slice_height_cm']<=10):
        raise ValueError('Axial slice height outside supported range')
    if case['max_abs_delta_k_pcm']<=0 or case['max_k_sigma_pcm']<=0:
        raise ValueError('Comparison limits must be positive')
    limit = 3.0 if case['exercise']=='1a' else .5
    if not 0 < case['temperature_tolerance_K'] <= limit:
        raise ValueError('Temperature tolerance exceeds the documented data approximation')


def pin_map(pitch=1.88):
    corners = {(10, 0), (-10, 0), (0, 10), (0, -10), (10, -10), (-10, 10)}
    pins, number = [], 0
    for r in range(10, -11, -1):
        for q in range(-10, 11):
            ring = max(abs(q), abs(r), abs(q + r))
            if ring > 10:
                continue
            kind = 'fuel'
            if ring <= 1:
                kind = 'central_graphite'
            elif (q - r) % 3 == 0:
                kind = 'small_coolant' if q*q + q*r + r*r == 3 else 'large_coolant'
            elif (q, r) in corners:
                kind = 'corner_graphite'
            numbered = kind in ('fuel', 'corner_graphite')
            number += int(numbered)
            pins.append(dict(q=q, r=r, x=pitch*(q+r/2), y=pitch*math.sqrt(3)*r/2,
                             kind=kind, pin=number if numbered else None))
    return pins


def audit_layout(spec):
    d = spec['dimensions']
    pins = pin_map(d['pitch_cm'])
    counts = dict(Counter(p['kind'] for p in pins))
    expected = dict(fuel=210, large_coolant=102, small_coolant=6,
                    central_graphite=7, corner_graphite=6)
    if counts != expected:
        raise ValueError(f'Pin count mismatch: {counts}')
    # Distance to each face of a flat-top regular hexagon, minus hole radius.
    apothem = d['block_flat_to_flat_cm']/2
    minimum_margin = math.inf
    for p in pins:
        if p['kind'] in ('central_graphite', 'corner_graphite'):
            continue
        radius = d['large_coolant_radius_cm'] if p['kind']=='large_coolant' else d['gap_radius_cm']
        for angle in (30, 90, 150, 210, 270, 330):
            a = math.radians(angle)
            margin = apothem - (p['x']*math.cos(a) + p['y']*math.sin(a)) - radius
            minimum_margin = min(minimum_margin, margin)
        if minimum_margin <= 0:
            raise ValueError('Hole crosses the graphite block boundary')
    if 2*d['large_coolant_radius_cm'] >= d['pitch_cm']:
        raise ValueError('Neighboring holes overlap')
    # Independent labeled anchors transcribed from Figure III-3.
    anchors = {2:(-9,10), 18:(-8,8), 84:(-2,2), 103:(-10,0),
               133:(2,-2), 199:(8,-8), 215:(9,-10), 216:(10,-10)}
    numbered = {p['pin']:p for p in pins if p['pin']}
    for number, coord in anchors.items():
        if (numbered[number]['q'], numbered[number]['r']) != coord:
            raise ValueError(f'Pin {number} is misnumbered')
    return dict(counts=counts, minimum_hole_face_margin_cm=minimum_margin,
                labeled_anchors_checked=len(anchors), analytic_checks='passed')


def timesteps(targets, max_step):
    """Burnup increments; resolve early poison buildup, then cap interval size."""
    if not targets or targets[0] != 0 or max_step <= 0:
        raise ValueError('Schedule must start at zero with positive maximum step')
    if any(b <= a for a,b in zip(targets, targets[1:])):
        raise ValueError('Burnup targets must increase strictly')
    endpoints = set(targets)
    endpoints.update(b for b in (.01,.05,.1,.2) if b < targets[-1])
    result, previous = [], 0.
    for end in sorted(endpoints)[1:]:
        count = math.ceil((end-previous)/max_step)
        result.extend([(end-previous)/count]*count)
        previous = end
    return result
