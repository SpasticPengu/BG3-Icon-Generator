"""Phase 5 look-ahead (D39): can FLUX.2 klein 4B, with no LoRA, draw objects no game icon shows as white line art?
Runs in the project venv (CUDA torch + diffusers 0.41; Anaconda's torch is CPU-only):
    .venv/Scripts/python.exe research/probes/klein_unseen.py [SIZE] [SEEDS]      (defaults 512, 2)
Weights: models/FLUX.2-klein-4B (distilled, 4 steps). Writes outputs/klein_unseen/<object>_<seed>.png and the labelled
sheet outputs/klein_unseen.png; logs seconds per image and peak VRAM. Objects = 0 of 1,083 motifs (5.3's list)."""
import sys
import time
from pathlib import Path

import torch
from diffusers import Flux2KleinPipeline
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OBJECTS = ["lantern", "candle", "mirror", "ladder", "cauldron", "anvil", "clock", "compass", "lock", "dice", "throne",
           "mushroom"]
PROMPT = ("A fantasy game ability icon of a {}, drawn as bold white line art on a pure black background, centred, "
          "clean even strokes, no colour, no text, no frame")


def main(size=512, seeds=2):
    out = ROOT / "outputs" / "klein_unseen"
    out.mkdir(parents=True, exist_ok=True)
    t = time.time()
    pipe = Flux2KleinPipeline.from_pretrained(ROOT / "models" / "FLUX.2-klein-4B", dtype=torch.bfloat16)
    free = torch.cuda.mem_get_info()[0] / 2**30
    # ponytail: whole-model offload needs the 7.75 GB transformer + activations on the card at once; with less free,
    # stream layers (slow). Group offload is the faster middle if this gets used a lot.
    whole = free > 8.5
    (pipe.enable_model_cpu_offload if whole else pipe.enable_sequential_cpu_offload)()
    print(f"loaded in {time.time() - t:.0f} s, {free:.1f} GB free -> {'model' if whole else 'sequential'} offload",
          flush=True)
    tiles = []
    for o in OBJECTS:
        for s in range(seeds):
            t = time.time()
            im = pipe(prompt=PROMPT.format(o), height=size, width=size, num_inference_steps=4,
                      generator=torch.Generator("cpu").manual_seed(s)).images[0]
            im.save(out / f"{o}_{s}.png")
            tiles.append((f"{o} {s}", im))
            print(f"{o} seed {s}: {time.time() - t:.1f} s, peak VRAM {torch.cuda.max_memory_allocated() / 2**30:.1f} GB",
                  flush=True)
    c, w = seeds * 4, 256
    rows = -(-len(tiles) // c)
    sheet = Image.new("RGB", (c * w, rows * (w + 20)), "#202020")
    d = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(tiles):
        x, y = i % c * w, i // c * (w + 20)
        sheet.paste(im.resize((w, w), Image.LANCZOS), (x, y + 20))
        d.text((x + 4, y + 4), label, fill="white")
    sheet.save(ROOT / "outputs" / "klein_unseen.png")
    print("sheet: outputs/klein_unseen.png", flush=True)


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:3]))
