"""Print kohya/safetensors metadata of LoRA files (base model, dims, dataset tags)."""
import json, struct, sys

KEYS = ["ss_sd_model_name", "ss_base_model_version", "ss_v2", "ss_network_module", "ss_network_dim",
        "ss_network_alpha", "ss_resolution", "ss_num_train_images", "ss_num_epochs", "ss_max_train_steps",
        "ss_learning_rate", "ss_unet_lr", "ss_text_encoder_lr", "ss_optimizer", "ss_lr_scheduler",
        "ss_noise_offset", "ss_multires_noise_iterations", "ss_clip_skip", "ss_caption_dropout_rate",
        "ss_keep_tokens", "ss_training_comment", "ss_output_name", "modelspec.architecture", "modelspec.title",
        "ss_bucket_info", "ss_datasets", "ss_mixed_precision", "ss_training_started_at"]

for path in sys.argv[1:]:
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(n))
    meta = hdr.get("__metadata__", {})
    tensors = [k for k in hdr if k != "__metadata__"]
    print("=" * 80, "\n", path, f"\n tensors={len(tensors)} sample={tensors[:3]}")
    for k in KEYS:
        if k in meta:
            v = meta[k]
            print(f"  {k}: {v[:600] if isinstance(v, str) else v}")
    tf = meta.get("ss_tag_frequency")
    if tf:
        tf = json.loads(tf)
        for ds, tags in tf.items():
            top = sorted(tags.items(), key=lambda kv: -kv[1])
            print(f"  [tags] dataset '{ds}': {len(tags)} distinct tags; top 60:")
            print("   ", ", ".join(f"{t}({c})" for t, c in top[:60]))
    other = [k for k in meta if k not in KEYS and k != "ss_tag_frequency"]
    print("  other keys:", other[:80])
