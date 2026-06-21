"""MediaGen: text -> image via the resolved best image model."""
import argparse, json, sys
import falkit as fal
from falkit import GuidedError

TASK = "image"


def build_request(prompt, resolution="2K", n_images=1) -> dict:
    return {"prompt": prompt, "num_images": n_images,
            "resolution": resolution, "output_format": "png"}


def run(prompt, out_path, resolution="2K", tier="best", model=None, dry_run=False) -> dict:
    endpoint = fal.resolve_model(TASK, tier=tier, override=model)
    payload = build_request(prompt, resolution)
    est = fal.estimate_cost(TASK, resolution=resolution)
    if dry_run:
        return {"endpoint": endpoint, "payload": payload, "est_cost": est}
    fal.load_fal_key()
    result = fal.subscribe(endpoint, payload)
    url = result["images"][0]["url"]
    fal.download(url, out_path)
    return {"endpoint": endpoint, "image": out_path, "remote_url": url, "est_cost": est}


def main():
    ap = argparse.ArgumentParser(description="Generate an image from a (pre-written) prompt.")
    ap.add_argument("prompt")
    ap.add_argument("--out", default="mediagen_image.png")
    ap.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"])
    ap.add_argument("--tier", default="best", choices=["best", "cheap"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        print(json.dumps(run(args.prompt, args.out, args.resolution, args.tier,
                             args.model, args.dry_run), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
