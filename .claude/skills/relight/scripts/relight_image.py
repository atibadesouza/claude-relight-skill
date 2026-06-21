"""Generate a relit still from the source frame + optional reference via Fal Nano Banana Pro."""
import argparse
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError, estimate_image_cost, load_fal_key

try:
    import fal_client
except ImportError:
    fal_client = None

ENDPOINT = "fal-ai/nano-banana-pro/edit"

CINEMATIC_TEMPLATE = (
    "Relight and re-environment this person. Keep their exact face, identity, "
    "clothing, pose, and framing from the first image. Apply cinematic three-point "
    "lighting with a warm, flattering key light and soft fill; gentle rim light to "
    "separate the subject; natural shadow falloff; subtle film color grade; shallow "
    "depth of field. Make the subject look attractive, warm, and professional. "
    "Background and scene: {user_prompt}. Photorealistic, no distortion of the face, "
    "no text or watermarks."
)


def build_image_request(frame_url, reference_url, user_prompt, resolution="2K") -> dict:
    image_urls = [frame_url]
    if reference_url:
        image_urls.append(reference_url)
    return {
        "prompt": CINEMATIC_TEMPLATE.format(user_prompt=user_prompt),
        "image_urls": image_urls,
        "resolution": resolution,
        "num_images": 1,
    }


def run(frame_path, reference_path, user_prompt, out_path, resolution="2K", dry_run=False) -> dict:
    if dry_run:
        payload = build_image_request(frame_path, reference_path, user_prompt, resolution)
        return {"endpoint": ENDPOINT, "payload": payload, "est_cost": estimate_image_cost(resolution)}
    if fal_client is None:
        raise GuidedError("fal-client not installed. Run install.ps1 or pip install -r requirements.txt.")
    load_fal_key()
    frame_url = fal_client.upload_file(frame_path)
    reference_url = fal_client.upload_file(reference_path) if reference_path else None
    payload = build_image_request(frame_url, reference_url, user_prompt, resolution)
    result = fal_client.subscribe(ENDPOINT, arguments=payload, with_logs=False)
    url = result["images"][0]["url"]
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)
    return {"endpoint": ENDPOINT, "image": out_path, "remote_url": url,
            "est_cost": estimate_image_cost(resolution)}


def main():
    ap = argparse.ArgumentParser(description="Relight a frame into a new environment.")
    ap.add_argument("frame")
    ap.add_argument("prompt")
    ap.add_argument("--reference", default=None)
    ap.add_argument("--out", default="relit_still.png")
    ap.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        import json
        print(json.dumps(run(args.frame, args.reference, args.prompt, args.out,
                             args.resolution, args.dry_run), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
