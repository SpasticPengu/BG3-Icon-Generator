"""5.2 / D39 shipping path: an AI Toolkit LoRA (trained on klein base 4B) in diffusers, on the distilled FLUX.2-klein-4B
(4 steps) at several LoRA strengths and on the base model it was trained on (BFL single file, STEPS steps, guidance 4),
the run's sample prompts (config.yaml beside the LoRA), seed 42. Logs seconds per image and peak VRAM.
    .venv/Scripts/python.exe research/probes/klein_lora.py LORA.safetensors OUT.png [SCALE,...] [BASE_STEPS]
       (defaults 1,1.5 and 28; rows: distilled no LoRA | distilled x each scale | base x 1; BASE_STEPS 0 skips the base)"""
import sys, time
from pathlib import Path

import torch
import yaml
from diffusers import Flux2KleinPipeline, Flux2Transformer2DModel
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def row(pipe, prompts, label, steps, guidance):
    out = []
    for i, p in enumerate(prompts):
        t = time.time()
        out.append(pipe(prompt=p, height=512, width=512, num_inference_steps=steps, guidance_scale=guidance,
                        generator=torch.Generator("cpu").manual_seed(42)).images[0])
        print(f"{label} {i}: {time.time() - t:.1f} s, peak {torch.cuda.max_memory_allocated() / 2**30:.1f} GB", flush=True)
    return out


def main(lora, out, scales="1,1.5", base_steps="28"):
    cfg = yaml.safe_load((Path(lora).parent / "config.yaml").read_text(encoding="utf-8"))
    prompts = [x["prompt"] for x in cfg["config"]["process"][0]["sample"]["samples"]]
    rows = []
    pipe = Flux2KleinPipeline.from_pretrained(ROOT / "models" / "FLUX.2-klein-4B", dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()
    rows.append(row(pipe, prompts, "distilled no LoRA", 4, 1.0))
    pipe.load_lora_weights(lora, adapter_name="icon")
    for s in map(float, scales.split(",")):
        pipe.set_adapters(["icon"], [s])
        rows.append(row(pipe, prompts, f"distilled LoRA x{s}", 4, 1.0))
    if int(base_steps):
        del pipe
        torch.cuda.empty_cache()
        tr = Flux2Transformer2DModel.from_single_file(
            str(ROOT / "models" / "FLUX.2-klein-base-4B" / "flux-2-klein-base-4b.safetensors"), dtype=torch.bfloat16,
            config=str(ROOT / "models" / "FLUX.2-klein-base-4B"), subfolder="transformer")
        pipe = Flux2KleinPipeline.from_pretrained(ROOT / "models" / "FLUX.2-klein-4B", transformer=tr, dtype=torch.bfloat16,
                                                  is_distilled=False)
        pipe.enable_model_cpu_offload()
        pipe.load_lora_weights(lora)
        rows.append(row(pipe, prompts, f"base LoRA x1 {base_steps} steps", int(base_steps), 4.0))
    s = 224
    sheet = Image.new("RGB", (len(prompts) * s, len(rows) * s))
    for r, ims in enumerate(rows):
        for c, im in enumerate(ims):
            sheet.paste(im.resize((s, s), Image.LANCZOS), (c * s, r * s))
    sheet.save(out)
    print(f"sheet: {out}", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:5])
