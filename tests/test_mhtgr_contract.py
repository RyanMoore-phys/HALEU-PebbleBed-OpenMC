"""Pure geometry arithmetic and report tests; no OpenMC imports or simulation."""
import copy
import json
import math
from pathlib import Path
import unittest

from benchmarks.mhtgr350.layout import audit_layout, pin_map, timesteps, validate_case
from benchmarks.mhtgr350.compare import compare_rows

ROOT=Path(__file__).resolve().parents[1]
SPEC=json.loads((ROOT/'benchmarks/mhtgr350/specification.json').read_text())
REF=json.loads((ROOT/'benchmarks/mhtgr350/reference.json').read_text())


class GeometryContract(unittest.TestCase):
    def test_counts_and_reference_anchors(self):
        self.assertEqual(audit_layout(SPEC)['counts']['fuel'],210)

    def test_all_holes_pairwise_nonoverlap(self):
        pins=[p for p in pin_map() if p['kind'] not in ('central_graphite','corner_graphite')]
        for i,p in enumerate(pins):
            for q in pins[i+1:]:
                rp=.794 if p['kind']=='large_coolant' else .635
                rq=.794 if q['kind']=='large_coolant' else .635
                self.assertGreater(math.hypot(p['x']-q['x'],p['y']-q['y']),rp+rq)

    def test_rotation_preserves_types(self):
        pins=pin_map(); lookup={(p['q'],p['r']):p['kind'] for p in pins}
        for p in pins:
            self.assertEqual(p['kind'],lookup[-p['r'],p['q']+p['r']])

    def test_numbering_includes_graphite_corners(self):
        numbered=[p['pin'] for p in pin_map() if p['pin']]
        self.assertEqual(numbered,list(range(1,217)))

    def test_overlap_and_wrong_pitch_rejected(self):
        s=copy.deepcopy(SPEC);s['dimensions']['pitch_cm']=1
        with self.assertRaises(ValueError):audit_layout(s)
        s=copy.deepcopy(SPEC);s['dimensions']['pitch_cm']=3
        with self.assertRaises(ValueError):audit_layout(s)

    def test_schedule_retains_every_reference_point(self):
        targets=SPEC['burnup_MWd_kgHM'];steps=timesteps(targets,1)
        endpoints=[0]
        for step in steps:endpoints.append(endpoints[-1]+step)
        for target in targets:self.assertTrue(any(abs(t-target)<1e-8 for t in endpoints))
        self.assertAlmostEqual(sum(steps),120)
        self.assertLessEqual(max(steps),1)
        self.assertAlmostEqual(steps[0],.01)

    def test_cases_match_exercises(self):
        for path in (ROOT/'cases').glob('mhtgr-*.json'):validate_case(json.loads(path.read_text()))
        c=json.loads((ROOT/'cases/mhtgr-cold.json').read_text());c['temperature_K']=1200
        with self.assertRaises(ValueError):validate_case(c)


class ComparisonContract(unittest.TestCase):
    def run_compare(self,actual,targets=None):
        return compare_rows('1a',targets or [0],actual,REF,500,50)

    def test_matching_result_passes_screen_only(self):
        rows=self.run_compare([dict(burnup=0,k=1.236,sigma=.0001)])
        self.assertTrue(rows[0]['screening_pass'])
        self.assertEqual(rows[0]['delta_k_pcm'],0)

    def test_large_bias_and_imprecise_results_fail(self):
        for k,sigma in [(1.25,.0001),(1.236,.001)]:
            self.assertFalse(self.run_compare([dict(burnup=0,k=k,sigma=sigma)])[0]['screening_pass'])

    def test_missing_duplicate_nan_results_fail(self):
        good=dict(burnup=0,k=1.236,sigma=.0001)
        for actual in [[],[good,good],[dict(good,k=float('nan'))],[dict(good,sigma=0)]]:
            with self.assertRaises(ValueError):self.run_compare(actual)

    def test_no_interpolation_or_wrong_exercise_matching(self):
        with self.assertRaises(ValueError):self.run_compare([dict(burnup=0,k=1.236,sigma=.0001)],[.5])

    def test_table_means_consistent_with_published_code_values(self):
        for exercise in ('1a','2a'):
            for row in REF[exercise]:
                mean=sum(row[c] for c in ('HELIOS','DeCART','McCARD','SERPENT'))/4
                self.assertLess(abs(row['mean']-mean),2e-5)

    def test_delta_k_is_distinct_from_reactivity(self):
        row=self.run_compare([dict(burnup=0,k=1.237,sigma=.0001)])[0]
        self.assertAlmostEqual(row['delta_k_pcm'],100)
        self.assertNotAlmostEqual(row['delta_rho_pcm'],100)


if __name__=='__main__':unittest.main()
