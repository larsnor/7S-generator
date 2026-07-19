"""Stdlib tests:  python3 -m unittest discover -s tests"""
import os
import tempfile
import unittest
from datetime import datetime

from corpusgen import generate
from corpusgen.corpus import Corpus
from corpusgen.mgrs import latlon_to_mgrs

CS = ["AQ", "BQ", "CQ", "DQ"]


def _build(out, days=7, reports=120, seed=1):
    return generate.build_normal(out=out, lat=60.345, lon=17.422, radius=3.0, area="airport",
                                 start=datetime(2026, 6, 15), days=days, callsigns=CS,
                                 seed=seed, reports=reports, obj_name="fältet")


class TestMgrs(unittest.TestCase):
    def test_forward_matches_known_vallinge_grid(self):
        self.assertEqual(latlon_to_mgrs(59.2615, 17.7135), "33VXF5468572319")
        self.assertTrue(latlon_to_mgrs(60.345, 17.422).startswith("33V"))


class TestGenerate(unittest.TestCase):
    def test_normal_corpus_is_valid_7s(self):
        with tempfile.TemporaryDirectory() as d:
            c = _build(d)
            self.assertEqual(len(c.ground_truth), 120)
            self.assertTrue(all(r["truth"] == "civil" for r in c.ground_truth))
            self.assertEqual(len(c.meta["locations"]), 16)   # 4 callsigns × 4
            for r in c.ground_truth[:25]:
                with open(os.path.join(d, r["file"]), encoding="utf-8") as fh:
                    txt = fh.read()
                self.assertIn("typ: 7S-rapport", txt)
                self.assertIn("**Händelse:**", txt)

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a, b = _build(d1), _build(d2)
            self.assertEqual([r["id"] for r in a.ground_truth],
                             [r["id"] for r in b.ground_truth])

    def test_area_frequency_scales(self):
        with tempfile.TemporaryDirectory() as urb, tempfile.TemporaryDirectory() as forest:
            u = generate.build_normal(out=urb, lat=59.0, lon=18.0, radius=3, area="urban",
                                      start=datetime(2026, 7, 1), days=10, callsigns=CS, seed=1)
            f = generate.build_normal(out=forest, lat=59.0, lon=18.0, radius=3, area="forest",
                                      start=datetime(2026, 7, 1), days=10, callsigns=CS, seed=1)
            self.assertGreater(len(u.ground_truth), 3 * len(f.ground_truth))


class TestAugment(unittest.TestCase):
    def test_hostiles(self):
        with tempfile.TemporaryDirectory() as d:
            _build(d, days=14, reports=200)
            n = generate.add_hostiles(Corpus.load(d), "recon", count=None, seed=3)
            self.assertTrue(2 <= n <= 10, n)
            gt = Corpus.load(d).ground_truth
            hostiles = [r for r in gt if r["truth"] == "hostile"]
            self.assertGreaterEqual(len(hostiles), n)                    # each appears ≥1×
            self.assertTrue(all(r["subtype"] == "recon" for r in hostiles))
            self.assertEqual(len({r["member"] for r in hostiles}), n)    # n distinct members

    def test_protesters_cluster(self):
        with tempfile.TemporaryDirectory() as d:
            _build(d, days=14, reports=200)
            m = generate.add_protesters(Corpus.load(d), "demonstranter", count=8, seed=5)
            self.assertEqual(m, 8)
            prot = [r for r in Corpus.load(d).ground_truth if r["truth"] == "protester"]
            self.assertEqual(len(prot), 8)
            self.assertEqual(len({r["member"] for r in prot}), 1)        # one group


class TestCraftFacit(unittest.TestCase):
    def test_craft_word_boundary(self):
        # "Bussresenärer" is people at a stop, not a bus; "Se bild." has no craft.
        self.assertEqual(generate._craft_of({"handelse": "Bussresenärer väntade vid hållplatsen."}), [])
        self.assertEqual(generate._craft_of({"handelse": "Se bild."}), [])
        self.assertEqual(generate._craft_of({"handelse": "Buss släppte av personal vid bommen."}), ["buss"])
        self.assertEqual(generate._craft_of({"handelse": "Traktor plöjde fältet."}), ["traktor"])
        self.assertEqual(generate._craft_of({"handelse": "Skåpbil backade mot grinden."}), ["lastbil"])
        self.assertEqual(generate._craft_of({"handelse": "Drönare hovrade över fältet."}), ["drönare"])
        self.assertEqual(
            generate._craft_of({"handelse": "Bogserbåt assisterade fartyg i rännan."}), ["båt", "fartyg"])

    def test_civil_corpus_carries_craft_facit(self):
        with tempfile.TemporaryDirectory() as d:
            c = _build(d, days=14, reports=300)
            tagged = [r for r in c.ground_truth if r.get("craft")]
            self.assertGreater(len(tagged), 0, "expected craft-tagged civil reports")
            types = {t for r in tagged for t in r["craft"]}
            # airport civil pool has tractors, delivery vans, cyclists, aircraft
            self.assertIn("traktor", types)
            self.assertIn("flygplan", types)

    def test_hostile_craft_and_water_gating(self):
        # Coastal corpus: recon pool INCLUDES boat behaviours; some hostile rows
        # should be craft-tagged (drone or boat) with enough members.
        with tempfile.TemporaryDirectory() as d:
            generate.build_normal(out=d, lat=59.663, lon=18.925, radius=3.0, area="coastal",
                                  start=datetime(2026, 6, 15), days=14, callsigns=CS,
                                  seed=1, reports=50, obj_name="objektet")
            generate.add_hostiles(Corpus.load(d), "recon", count=10, seed=3)
            gt = Corpus.load(d).ground_truth
            hostile_craft = {t for r in gt if r["truth"] == "hostile" for t in r.get("craft", [])}
            self.assertTrue({"drönare", "båt"} & hostile_craft,
                            f"expected drone/boat hostile craft, got {hostile_craft}")
        # Inland corpus: the water lines are gated OUT — no hostile boats ever.
        with tempfile.TemporaryDirectory() as d:
            generate.build_normal(out=d, lat=60.0, lon=15.0, radius=3.0, area="rural",
                                  start=datetime(2026, 6, 15), days=14, callsigns=CS,
                                  seed=1, reports=50, obj_name="objektet")
            generate.add_hostiles(Corpus.load(d), "recon", count=10, seed=3)
            gt = Corpus.load(d).ground_truth
            hostile_craft = {t for r in gt if r["truth"] == "hostile" for t in r.get("craft", [])}
            self.assertNotIn("båt", hostile_craft, "no water in a rural area")
            self.assertNotIn("fartyg", hostile_craft)


class TestCliAoi(unittest.TestCase):
    def _parse(self, *aoi_tokens):
        from corpusgen.cli import build_parser
        args = build_parser().parse_args(
            ["generate", "--aoi", *aoi_tokens, "--from", "2026-06-15", "--out", "/tmp/x"])
        return args.aoi

    def test_aoi_accepts_common_forms(self):
        self.assertEqual(self._parse("59.664,18.925"), (59.664, 18.925))      # canonical
        self.assertEqual(self._parse("59.664,", "18.925"), (59.664, 18.925))  # space after comma
        self.assertEqual(self._parse("59.664", "18.925"), (59.664, 18.925))   # space separator
        self.assertEqual(self._parse("59.664, 18.925"), (59.664, 18.925))     # quoted, spaced

    def test_aoi_rejects_bad_input(self):
        with self.assertRaises(SystemExit):      # argparse exits on a bad value
            self._parse("59.664")                # only one number
        with self.assertRaises(SystemExit):
            self._parse("abc,def")               # non-numeric


if __name__ == "__main__":
    unittest.main()
