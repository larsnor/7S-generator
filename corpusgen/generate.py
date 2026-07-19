"""Generation logic — pure functions over the content tables.

`build_normal` creates a corpus of benign activity for an area; `add_hostiles` and
`add_protesters` inject a threat / noise layer into an existing corpus. All three
are seedable and deterministic."""
import random as _random
import re as _re
import uuid as _uuid
from datetime import datetime, timedelta

from . import geo
from .content import (AREAS, SEASONS, HOSTILES, PROTESTERS, CARS, DOGS, COLOURS,
                      VARIED_TELLS, DECOY_CLOTHING, CRAFT_WORDS, WATER_AREAS)
from .corpus import Corpus
from .imagebank import ImageBank
from .mgrs import latlon_to_mgrs
from .render import tnr_from, iso


def _attach_entry(corpus, rec, bank, entry, obsidian):
    """Turn `rec` into a 'Se bild.' photo report carrying a specific bank image,
    copying it into the corpus and recording its facit. The typed text is dropped —
    this is the VLM-only case the situational tool's vision layer exists for."""
    folder = _attachment_dir(rec) if obsidian else "attachments"
    bank.copy(entry, corpus.path / folder)
    rec["image"] = f"{folder}/{entry['file']}"
    rec["image_truth"] = entry["truth"]
    rec["handelse"] = "Se bild."
    rec.pop("symbol", None)
    rec["plate"] = None  # a plate now lives only in the PHOTO, never typed


def _attach_photo(corpus, rec, bank, rng, roles, obsidian):
    """As _attach_entry, but drawing a random bank image of one of `roles`.
    Returns True if a photo was attached."""
    entry = bank.pick(rng, roles)
    if not entry:
        return False
    _attach_entry(corpus, rec, bank, entry, obsidian)
    return True


def _uid(rng):
    return str(_uuid.UUID(int=rng.getrandbits(128), version=4))


def _craft_of(rec):
    """Canonical craft types mentioned in the record's FINAL Händelse ⊕ Symbol
    (word-boundary matched, Swedish-aware) — the craft facit. Call after any
    photo attachment (which replaces the text with 'Se bild.')."""
    text = " ".join(filter(None, [rec.get("handelse"), rec.get("symbol")])).lower()
    found = []
    for word, key in CRAFT_WORDS.items():
        if key not in found and _re.search(r"(?<![a-zåäö0-9])" + word + r"(?![a-zåäö0-9])", text):
            found.append(key)
    return sorted(found)


def _stamp_craft(rec):
    craft = _craft_of(rec)
    if craft:
        rec["craft"] = craft


def season_of(month):
    for name, s in SEASONS.items():
        if month in s["months"]:
            return name
    return "sommar"


def build_locations(lat, lon, radius, area, callsigns, rng, per=4):
    """`per` named locations per callsign, each in that callsign's bearing wedge."""
    places = AREAS[area]["places"][:]
    rng.shuffle(places)
    n = len(callsigns)
    width = 360 / n
    locs, pi = [], 0
    for i, cs in enumerate(callsigns):
        for _ in range(per):
            bearing = rng.uniform(i * width, (i + 1) * width)
            dist = radius * (rng.random() ** 0.5)
            plat, plon = geo.offset_point(lat, lon, bearing, dist)
            name = places[pi % len(places)]
            pi += 1
            locs.append({"callsign": cs, "sector": i, "name": name,
                         "lat": plat, "lon": plon, "mgrs": latlon_to_mgrs(plat, plon, sep=" ")})
    return locs


def _attachment_dir(rec):
    """Per-message attachment folder, matching the source app's shape:
    <signaltime>_<DDHHMM>-<sender>."""
    ts = datetime.fromisoformat(rec.get("signal_tidpunkt") or rec["tidpunkt"])
    sender = rec.get("sender") or rec["uuid"]
    return f"{ts:%Y%m%d%H%M%S}_{ts:%d%H%M}-{sender}"


def _civ_time(start, days, rng, day_band):
    lo, hi = day_band
    hour = min(hi, max(lo, int(rng.gauss((lo + hi) / 2, (hi - lo) / 5))))
    return start + timedelta(days=rng.randrange(days), hours=hour, minutes=rng.randrange(60))


def _threat_time(start, days, rng, night_bias):
    if rng.random() < night_bias:
        hour = rng.choice([22, 22, 23, 0, 1, 4, 5, 5, 6, 21])
    else:
        hour = rng.randrange(6, 22)
    return start + timedelta(days=rng.randrange(days), hours=hour, minutes=rng.randrange(60))


def _new_record(dt, loc, rng, platoon_uuid):
    if rng.random() < 0.9:  # Signal is the default channel
        sig = dt + timedelta(minutes=rng.randint(1, 3), seconds=rng.randint(0, 59))
        tnr, sigt, sender = tnr_from(sig), iso(sig), platoon_uuid[loc["callsign"]]
    else:
        tnr, sigt, sender = tnr_from(dt), None, None
    grid_only = rng.random() < 0.5
    return {
        "uuid": _uid(rng), "tnr": tnr, "tidpunkt": iso(dt), "signal_tidpunkt": sigt,
        "sender": sender, "callsign": loc["callsign"], "stund": tnr_from(dt),
        "stalle": loc["mgrs"] if grid_only else f'{loc["mgrs"]}, {loc["name"]}',
        "plats": loc["mgrs"] if grid_only else loc["name"],
        "lat": None if grid_only else loc["lat"], "lon": None if grid_only else loc["lon"],
        "sector": loc["sector"], "name": loc["name"], "plate": None,
    }


# --- normal activity --------------------------------------------------------
def build_normal(out, lat, lon, radius, area, start, days, callsigns, seed,
                 reports=None, obj_name="objektet", images=False, obsidian=False,
                 photos=False):
    rng = _random.Random(seed)
    prof = AREAS[area]
    season = season_of(start.month)
    smeta = SEASONS[season]
    locs = build_locations(lat, lon, radius, area, callsigns, rng)
    platoon_uuid = {cs: _uid(rng) for cs in callsigns}

    if reports is None:
        reports = round(prof["reports_per_day"] * days * smeta["civ_mult"])

    corpus = Corpus.create(out, {
        "aoi": [lat, lon], "aoi_name": obj_name, "radius_km": radius, "area": area,
        "from": start.strftime("%Y-%m-%d"), "days": days, "callsigns": callsigns,
        "season": season, "seed": seed, "obsidian": obsidian,
        "locations": locs, "platoon_uuid": platoon_uuid,
    })
    render_plate = None
    if images:
        from .images import render_plate  # lazy: only needs Pillow with --images
    # Real-photo "Se bild" reports from the bundled synthetic bank (§6.7 VLM path).
    bank = ImageBank.load() if photos else None

    for _ in range(reports):
        loc = rng.choice(locs)
        rec = _new_record(_civ_time(start, days, rng, smeta["day"]), loc, rng, platoon_uuid)
        template = rng.choice(prof["civil"])
        if prof["vehicles"] and "{car}" in template and rng.random() < 0.5:
            rec["plate"] = _plate(rng)
            car = rng.choice(CARS) + f", reg {rec['plate']}"
        else:
            car = rng.choice(CARS)
        rec["handelse"] = template.format(car=car, dog=rng.choice(DOGS), colour=rng.choice(COLOURS))
        if rng.random() < 0.12:  # occasional benign appearance (season-appropriate)
            rec["symbol"] = f"{rng.choice(smeta['upper'])}, {rng.choice(smeta['accessory'])}"
        # A fraction of civil messages are photo-only ("Se bild") — benign scenes
        # and ordinary vehicles-with-plates a Home Guard soldier would snap.
        if bank and bank.has("benign", "plate") and rng.random() < 0.20:
            _attach_photo(corpus, rec, bank, rng, ["benign", "plate"], obsidian)
        elif images and rec["plate"]:  # else: a corroborating card of the typed plate
            folder = _attachment_dir(rec) if obsidian else "attachments"
            img_name = f"plate_{rec['uuid'][:8]}.jpg"
            d = corpus.path / folder
            d.mkdir(parents=True, exist_ok=True)
            render_plate(rec["plate"], d / img_name)
            rec["image"] = f"{folder}/{img_name}"
        _stamp_craft(rec)
        corpus.add(rec, "civil")

    corpus.save()
    return corpus


_LETTERS = "ABCDEFGHJKLMNPRSTUWXYZ"
def _plate(rng):
    a = "".join(rng.choice(_LETTERS) for _ in range(3))
    if rng.random() < 0.5:
        return a + "".join(rng.choice("0123456789") for _ in range(3))
    return a + "".join(rng.choice("0123456789") for _ in range(2)) + rng.choice(_LETTERS)


# --- hostiles ---------------------------------------------------------------
def add_hostiles(corpus, htype, count, seed, varied=False, photos=False):
    rng = _random.Random(seed)
    prof = HOSTILES[htype]
    bank = ImageBank.load() if photos else None
    obsidian = bool(corpus.meta.get("obsidian"))
    m = corpus.meta
    lat, lon = m["aoi"]
    start = datetime.strptime(m["from"], "%Y-%m-%d")
    days, obj = m["days"], m.get("aoi_name", "objektet")
    locs = m["locations"]
    platoon_uuid = m["platoon_uuid"]

    # near-AOI weighting
    ranked = sorted(locs, key=lambda l: geo.dist_km(lat, lon, l["lat"], l["lon"]))
    near = ranked[: max(1, len(ranked) * 3 // 5)]

    # Water behaviours (boat surveillance / landings) only where there IS water.
    behaviours = prof["behaviour"] + (
        prof.get("behaviour_water", []) if m.get("area") in WATER_AREAS else [])

    if count is None:
        count = rng.randint(2, 10)

    # Varied-marks (validation) mode: each MEMBER keeps ONE tell but every
    # appearance PARAPHRASES it, and the true tell is written to ground truth. This
    # makes soft re-id a real paraphrase task (not verbatim string matching) and
    # frees the truth from any recogniser's vocabulary.
    if varied:
        tell_ids = list(VARIED_TELLS)
        rng.shuffle(tell_ids)
        # a range of real gear colours — the recogniser only distinguishes dark/light,
        # so greens/blues expose the colour vocabulary too.
        colours = ["mörk", "svart", "ljus", "ljusgrå", "grön", "blå", "beige"]
        for i in range(count):
            member = f"H{i + 1}"
            tid = tell_ids[i % len(tell_ids)]
            pool = VARIED_TELLS[tid]["phrasings"]
            colour = rng.choice(colours)  # STABLE per member (their gear colour)
            for _ in range(rng.randint(*prof["appearances"])):
                loc = rng.choice(near if rng.random() < prof["near_bias"] else locs)
                rec = _new_record(_threat_time(start, days, rng, prof["night_bias"]), loc, rng, platoon_uuid)
                rec["handelse"] = rng.choice(behaviours).format(obj=obj)
                phrasing = rng.choice(pool).replace("{colour}", colour)
                rec["symbol"] = f"{rng.choice(DECOY_CLOTHING)}, {phrasing}"
                _stamp_craft(rec)
                corpus.add(rec, "hostile", subtype=htype, member=member, tells=[tid])
        corpus.save()
        return count

    marks = prof["marks"][:]
    rng.shuffle(marks)

    for i in range(count):
        member = f"H{i + 1}"
        mark = marks[i % len(marks)]
        # Each member may have ONE vehicle for the whole cell run — the SAME plate
        # photo then recurs across their appearances, so photo→plate→Job A can
        # re-identify the vehicle and link the pattern (the point of the test).
        member_vehicle = bank.pick(rng, ["plate"]) if bank and bank.has("plate") and rng.random() < 0.6 else None
        for _ in range(rng.randint(*prof["appearances"])):
            loc = rng.choice(near if rng.random() < prof["near_bias"] else locs)
            rec = _new_record(_threat_time(start, days, rng, prof["night_bias"]), loc, rng, platoon_uuid)
            rec["handelse"] = rng.choice(behaviours).format(obj=obj)
            rec["symbol"] = mark
            # A fraction of appearances arrive as "Se bild": the member's OWN
            # vehicle (recurring plate) or a surveillance shot (recon behaviour).
            if bank and rng.random() < 0.4:
                if member_vehicle and rng.random() < 0.5:
                    _attach_entry(corpus, rec, bank, member_vehicle, obsidian)
                elif bank.has("recon"):
                    _attach_photo(corpus, rec, bank, rng, ["recon"], obsidian)
            _stamp_craft(rec)
            corpus.add(rec, "hostile", subtype=htype, member=member)

    corpus.save()
    return count


# --- protesters (challenging civilians) -------------------------------------
def add_protesters(corpus, ptype, count, seed):
    rng = _random.Random(seed)
    prof = PROTESTERS[ptype]
    m = corpus.meta
    start = datetime.strptime(m["from"], "%Y-%m-%d")
    obj = m.get("aoi_name", "objektet")
    locs = m["locations"]
    platoon_uuid = m["platoon_uuid"]

    size = count if count is not None else rng.randint(*prof["size"])
    loc = rng.choice(locs)                       # a protest gathers at one place…
    day0 = rng.randrange(m["days"])
    hour0 = rng.randrange(9, 18)                 # …in daylight
    behaviour = rng.choice(prof["behaviour"]).format(obj=obj)

    for _ in range(size):
        dt = start + timedelta(days=day0, hours=hour0, minutes=rng.randrange(0, 90))
        rec = _new_record(dt, loc, rng, platoon_uuid)
        rec["handelse"] = behaviour
        rec["symbol"] = rng.choice(prof["marks"])
        _stamp_craft(rec)
        corpus.add(rec, "protester", subtype=ptype, member="protest-1")

    corpus.save()
    return size
