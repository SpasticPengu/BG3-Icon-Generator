"""Run an AI Toolkit job with klein 4B's text encoder read from models/qwen3-4b instead of the hub. That folder = hard links
to models/FLUX.2-klein-4B/text_encoder + tokenizer (stock Qwen3-4B, the encoder the app runs), so training sees the same
encoder and nothing is downloaded twice. AI Toolkit hard-codes "Qwen/Qwen3-4B" for klein (Flux2Klein4BModel).
    tools/ai-toolkit/venv/Scripts/python.exe train/run_aitk.py CONFIG.yaml"""
import os, runpy, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AITK = ROOT / "tools" / "ai-toolkit"
# configs write {ROOT} for this folder (no one's own paths in git); AI Toolkit gets a copy with it filled in
src = Path(sys.argv[1]).resolve()
filled = ROOT / "outputs" / f"aitk_{src.name}"
filled.parent.mkdir(parents=True, exist_ok=True)
filled.write_text(src.read_text(encoding="utf-8").replace("{ROOT}", ROOT.as_posix()), encoding="utf-8")
config = str(filled)
sys.path.insert(0, str(AITK))
os.chdir(AITK)
from extensions_built_in.diffusion_models.flux2.flux2_klein_model import Flux2Klein4BModel

Flux2Klein4BModel.flux2_klein_te_path = str(ROOT / "models" / "qwen3-4b")
print(f"[run_aitk] klein 4B text encoder: {Flux2Klein4BModel.flux2_klein_te_path}", flush=True)

# Log GPU memory and where each part sits after every device switch: the all-kinds run spilled to shared memory while
# caching text embeddings (only the encoder should be on the card then).
import torch
from toolkit.models.base_model import BaseModel

_preset = BaseModel.set_device_state_preset


def _logged_preset(self, preset):
    _preset(self, preset)
    dev = lambda m: str(next(m.parameters()).device) if m is not None else "-"
    te = self.text_encoder[0] if isinstance(self.text_encoder, list) else self.text_encoder
    print(f"[run_aitk] preset {preset}: {torch.cuda.memory_allocated() / 2**30:.2f} GiB allocated, "
          f"{torch.cuda.memory_reserved() / 2**30:.2f} reserved; unet {dev(self.unet)}, te {dev(te)}, "
          f"vae {dev(self.vae)}", flush=True)


BaseModel.set_device_state_preset = _logged_preset
sys.argv = ["run.py", config]
runpy.run_path(str(AITK / "run.py"), run_name="__main__")
