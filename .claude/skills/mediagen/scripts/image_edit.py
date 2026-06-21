"""MediaGen: edit/transform image(s) using reference image paths, identity-preserving."""
import argparse, json, sys
import falkit as fal
from falkit import GuidedError

TASK = "image_edit"


def build_request(prompt, image_urls, resolution="2K") -> dict:
    if not image_urls:
        raise GuidedError("image_edit needs at least one reference image path.")
    return {"prompt": prompt, "image_urls": list(image_urls),
            "resolution": resolution, "num_images": 1}


def run(prompt, image_paths, out_path, resolution="2K", tier="best", model=None, dry_run=False) -> dict:
    endpoint = fal.resolve_model(TASK, tier=tier, override=model)
    est = fal.estimate_cost(TASK, resolution=resolution)
    if dry_run:
        return {"endpoint": endpoint, "payload": build_request(prompt, image_paths, resolution), "est_cost": est}
    fal.load_fal_key()
    urls = [fal.upload_file(p) for p in image_paths]
    payload = build_request(prompt, urls, resolution)
    result = fal.subscribe(endpoint, payload)
    url = result["images"][0]["url"]
    fal.download(url, out_path)
    return {"endpoint": endpoint, "image": out_path, "remote_url": url, "est_cost": est}


def main():
    ap = argparse.ArgumentParser(description="Edit images using reference paths.")
    ap.add_argument("prompt")
    ap.add_argument("references", nargs="+")
    ap.add_argument("--out", default="mediagen_edit.png")
    ap.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"])
    ap.add_argument("--tier", default="best", choices=["best", "cheap"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        print(json.dumps(run(args.prompt, args.references, args.out, args.resolution,
                             args.tier, args.model, args.dry_run), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
