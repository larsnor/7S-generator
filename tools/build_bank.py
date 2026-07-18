#!/usr/bin/env python3
"""Build the FULLY SYNTHETIC image bank bundled with the generator (corpusgen/
imagebank/): benign people, recon/hostile people, and Swedish plate cards. All
synthetic → no GDPR / third-party-IP exposure, safe to commit and ship.

- People: SDXL-Turbo (photorealistic, on Apple MPS) via the fp16-fix VAE.
- Plates: the generator's own render_plate (clean Swedish plate cards, known text).

Run with a venv that has torch+diffusers (people) AND the generator importable
(plates):

    <imgen-venv>/bin/python tools/build_bank.py

Writes corpusgen/imagebank/*.jpg + corpusgen/imagebank/bank.json (role + facit).
Deterministic per seed. Re-runnable (overwrites).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BANK = REPO / "corpusgen" / "imagebank"
BANK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(REPO))

STYLE = (
    "photorealistic photo, full body visible, candid documentary style, "
    "overcast daylight, Swedish archipelago / countryside setting"
)
NEG = "cartoon, illustration, painting, low quality, deformed, cropped heads, text, watermark"

# --- benign people: standing/ordinary, NO threat behaviour -------------------
BENIGN = [
    ("a young man in a red jacket standing on a gravel road", ["röd jacka"]),
    ("a woman in a yellow raincoat walking a dog on a path", ["gul regnjacka"]),
    ("a middle-aged man in a blue checked shirt standing by a fence", ["blå rutig skjorta"]),
    ("an elderly woman in a purple coat with a shopping bag", ["lila kappa"]),
    ("two hikers with backpacks on a forest trail", ["ryggsäckar"]),
    ("a family with children by a jetty near boats", []),
    ("a man in overalls carrying firewood by a red barn", ["overall"]),
    ("a woman in a green jacket picking mushrooms in a forest", ["grön jacka"]),
    ("an elderly man in a grey coat and flat cap waiting at a bus stop", ["grå rock", "keps"]),
    ("a jogger in bright sportswear on a country lane", ["sportkläder"]),
    ("a couple in autumn clothing looking at a map by a lake", ["karta"]),
    ("a woman in a beige coat standing on a cobblestone street", ["beige kappa"]),
]

# --- recon / hostile people: surveillance behaviour ONLY (the photographable
#     kind; a soldier who sees sabotage intervenes, doesn't photograph it) ------
RECON = [
    ("a man looking through binoculars towards a building, forest edge", ["optik", "observation"]),
    ("a person photographing with a large telephoto camera lens on a hillside", ["optik"]),
    ("a man in dark clothing observing a gate from across the street", ["observation"]),
    ("a man writing in a notebook while watching a road, roadside", ["registrering", "observation"]),
    ("a person looking through a chain-link fence at an industrial yard", ["perimeter", "observation"]),
    ("a man with binoculars near a jetty watching boats in an archipelago", ["optik", "observation"]),
    ("a person crouched observing through a monocular in tall grass", ["optik", "observation"]),
    ("a man pacing and measuring along a fence line with a device", ["registrering", "perimeter"]),
    ("a man photographing a bridge with a camera, standing still", ["optik"]),
    ("a person in a parked-car window watching a driveway with binoculars", ["optik", "observation"]),
    ("a man lingering by a locked gate looking around repeatedly", ["dröjande", "perimeter"]),
    ("a person filming a harbour entrance with a handheld camera", ["optik"]),
]

# --- vehicles WITH a plate: an SDXL car (real scene, make+colour) with our known
#     plate COMPOSITED onto the bumper — a realistic photo, legible+known plate,
#     still fully synthetic. (colour_en, make_en, body, colour_sv, make_sv, setting, plate)
VEHICLES = [
    ("red", "Volvo", "estate car", "röd", "Volvo", "on a gravel driveway", "LUK221"),
    ("blue", "Audi", "sedan", "blå", "Audi", "on a town street", "TBF907"),
    ("silver", "Volkswagen", "hatchback", "silver", "Volkswagen", "in a parking lot", "MSD413"),
    ("black", "BMW", "SUV", "svart", "BMW", "on a forest road", "XRE58H"),
    ("white", "Toyota", "car", "vit", "Toyota", "by a harbour", "GPN640"),
    ("dark green", "Saab", "sedan", "mörkgrön", "Saab", "on a country lane", "KWZ192"),
    ("grey", "Mercedes", "van", "grå", "Mercedes", "in an industrial yard", "DHJ705"),
    ("blue", "Ford", "pickup truck", "blå", "Ford", "in a field", "VNC834"),
    ("beige", "Volvo", "vintage car", "beige", "Volvo", "by a red barn", "RAM019"),
    ("white", "Tesla", "car", "vit", "Tesla", "at a charging station", "FYT26B"),
    ("dark blue", "Skoda", "estate car", "mörkblå", "Skoda", "on a cobblestone street", "BEK550"),
    ("green", "Land Rover", "SUV", "grön", "Land Rover", "on a gravel road", "OLP377"),
]


def _pipe():
    import torch
    from diffusers import AutoencoderKL, AutoPipelineForText2Image

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16)
    pipe = AutoPipelineForText2Image.from_pretrained(
        "stabilityai/sdxl-turbo", vae=vae, torch_dtype=torch.float16, variant="fp16"
    ).to(device)
    pipe.enable_attention_slicing()
    return pipe


def gen_people(pipe, entries, prefix, role, out, catalog):
    import torch
    for i, (desc, marks) in enumerate(entries):
        g = torch.Generator(device="cpu").manual_seed(4200 + (7 if role == "recon" else 0) + i)
        img = pipe(
            prompt=f"{desc}, {STYLE}", negative_prompt=NEG,
            num_inference_steps=4, guidance_scale=0.0, width=768, height=768, generator=g,
        ).images[0]
        name = f"{prefix}_{i + 1:02d}.jpg"
        img.save(out / name, "JPEG", quality=90)
        behaviour = [m for m in marks if m in {"optik", "observation", "registrering", "perimeter", "dröjande", "kontraspaning"}]
        catalog.append({
            "file": name, "role": role,
            "truth": {"behaviour": behaviour, "marks": [m for m in marks if m not in behaviour], "persons": 1, "desc": desc},
        })
        print(f"wrote {name}")


def _plate_strip(plate, tmp):
    """Render our plate card and crop to a tight plate rectangle (Image)."""
    from PIL import Image
    from corpusgen.images import render_plate
    render_plate(plate, str(tmp), note="")
    return Image.open(tmp).convert("RGB").crop((36, 34, 484, 126))  # the plate rect


def gen_vehicles(pipe, vehicles, out, catalog):
    import torch
    for i, (col, make, body, col_sv, make_sv, setting, plate) in enumerate(vehicles):
        g = torch.Generator(device="cpu").manual_seed(8400 + i)
        # Straight-on rear view → the plate area is predictably centered low, so a
        # fixed-position composite lands on the bumper (and covers any plate SDXL
        # draws itself). "blank bumper" discourages SDXL's own (garbled) plate.
        prompt = (
            f"photo taken directly behind a parked {col} {make} {body}, rear of the "
            f"car fills the frame, blank rear bumper, no license plate, {setting}, {STYLE}"
        )
        car = pipe(prompt=prompt, negative_prompt=NEG + ", license plate text, numbers on bumper",
                   num_inference_steps=4, guidance_scale=0.0, width=768, height=768, generator=g).images[0]
        strip = _plate_strip(plate, out / "_tmp_plate.jpg")
        w, h = car.size
        pw = int(0.30 * w)
        ph = max(1, int(pw * strip.height / strip.width))
        car.paste(strip.resize((pw, ph)), ((w - pw) // 2, int(0.66 * h)))
        name = f"vehicle_{i + 1:02d}.jpg"
        car.save(out / name, "JPEG", quality=90)
        catalog.append({"file": name, "role": "plate", "truth": {"plate": plate, "vehicle": f"{col_sv} {make_sv}", "behaviour": []}})
        print(f"wrote {name} ({col} {make} / {plate})")
    (out / "_tmp_plate.jpg").unlink(missing_ok=True)


def main():
    pipe = _pipe()
    catalog = []
    gen_vehicles(pipe, VEHICLES, BANK, catalog)
    gen_people(pipe, BENIGN, "benign", "benign", BANK, catalog)
    gen_people(pipe, RECON, "recon", "recon", BANK, catalog)
    (BANK / "bank.json").write_text(json.dumps({"images": catalog}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    roles = {}
    for c in catalog:
        roles[c["role"]] = roles.get(c["role"], 0) + 1
    print(f"bank.json: {len(catalog)} images {roles}")


if __name__ == "__main__":
    main()
