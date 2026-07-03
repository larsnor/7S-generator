# 7S-generator — TODO

Deferred work for the standalone corpus generator.

- [ ] **More area types** — industrial estate, power plant, border crossing,
      railway yard, hospital. Add a profile to `corpusgen/content.py` (frequency,
      place names, civilian templates); the logic is untouched.
- [ ] **Richer hostility realism** — a shared team vehicle linking distinct
      hostiles; multi-phase campaigns (recon → sabotage); escalating tempo over the
      window; day/night patterns per type.
- [ ] **More varied prose** — broaden civilian/hostile/protester phrasings and
      per-area idioms so a corpus stresses open-vocabulary detectors, not just the
      fixed keyword list.
- [ ] **Offline gazetteer** — optional place-name → coordinate lookup for the AOI
      (so `--aoi` could take a name), usable air-gapped.
- [ ] **Packaging** — verify the `7s-generator` console entry point; consider PyPI.
