# Relight — a Claude Code skill

Turn flat, badly-lit talking-head footage into a cinematic, studio-lit shot in a new
environment — without leaving Claude Code. You give it a clip, a description of the look
you want, and (optionally) a reference photo. It picks the sharpest frame, generates a
relit still of you in the new environment, lets you approve it, then animates your original
footage in that look — preserving your motion and audio.

Inspired by the [Systems by Vic](https://www.youtube.com/watch?v=pZNQwzW_JjM) "Relight" workflow.

**Any length works.** Clips up to 10 seconds run in a single pass. Longer clips are
automatically split into 3–10s segments, each relit against the **same** approved still
(so the lighting and background stay consistent), then stitched back into one video.

---

## 👉 First time? Just tell Claude Code to read this file.

Open Claude Code in this folder and say:

> **"Read the README and set up the Relight skill for me."**

Claude will run all the setup below automatically, ask you for your Fal API key, verify the
environment, and tell you when you're ready to relight your first clip. You don't need to run
any commands yourself.

---

## For Claude Code — automated setup (run this when asked to read/set up this README)

**You (Claude Code) are responsible for getting this skill fully working. Do these steps in
order, then confirm readiness. Do not skip the verification.**

1. **Run the installer.** On Windows: `./install.ps1`. It installs ffmpeg (via winget),
   `pip install`s the Python deps in `.claude/skills/relight/requirements.txt`, symlinks the
   skill into `~/.claude/skills/relight`, and creates `.env` from `.env.example`.
   - On macOS/Linux (no `install.ps1`): install ffmpeg (`brew install ffmpeg` /
     `apt install ffmpeg`), run `pip install -r .claude/skills/relight/requirements.txt`,
     copy `.claude/skills/relight/.env.example` to `.claude/skills/relight/.env`.
   - **ffmpeg PATH gotcha:** winget often updates PATH but the current shell won't see it
     until restarted. If `ffmpeg`/`ffprobe` aren't found right after install, locate the
     binary (e.g. under `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\...\bin`) and
     prepend that dir to PATH for your commands, or tell the user to restart the shell.

2. **Get the Fal API key from the user.** Ask them to paste their key (from
   https://fal.ai/dashboard/keys — the models are paid, so they need credit). When they give
   it to you, **write it into `.claude/skills/relight/.env`** as `FAL_KEY=<their key>` using a
   file edit — **do not echo the key back into the chat.** Never commit `.env` (it is
   gitignored). If they'd rather not paste it, tell them to edit that file themselves.

3. **Verify the environment.** Run `python .claude/skills/relight/scripts/preflight.py`.
   Expect `READY`. If any line shows `[XX]`, fix it (install the missing dep, fix the PATH,
   or get the key) and re-run until it reports `READY`.

4. **Confirm and hand off.** Tell the user setup is complete and ask for their first job:
   a video file path, a description of the lighting/background they want, and (optionally) a
   reference image path. Then follow the skill's `SKILL.md` to run the relight (including the
   cost-approval gate before any paid step).

> The actual relight workflow lives in `.claude/skills/relight/SKILL.md` — that's your
> orchestration guide once setup is done.

## How it works

1. **Sharpest frame** — samples the clip and picks the clearest, non-blurry frame.
2. **Relit still** — Fal **Nano Banana Pro** places you in the new environment with baked-in
   cinematic, warm, flattering lighting.
3. **You approve** — see the still and the exact cost before anything is spent.
4. **Relit video** — Fal **Kling O1 video-to-video reference** animates your footage in the
   new look, preserving motion + audio and subtly animating the background.
5. **Deliver** — a finished MP4 in `relight-outputs/`.

## Requirements

- **Claude Code** (this is a Claude Code skill — it writes files locally, so it won't work in
  the regular Claude app).
- **Python 3.9+** on your PATH.
- A **Fal AI account + API key** with some credit: https://fal.ai/dashboard/keys
  (the models are paid — see Cost below).
- Windows (the installer is PowerShell; the Python scripts are cross-platform).

## Install

```powershell
git clone <this-repo> "Video Editing"
cd "Video Editing"
./install.ps1
```

`install.ps1` installs ffmpeg (via winget), installs the Python dependencies, symlinks the
skill into `~/.claude/skills/relight` (so it works from anywhere), and creates a `.env` file.

Then add your key — **edit the file, don't paste the key into chat**:

```
# .claude/skills/relight/.env
FAL_KEY=your_fal_key_here
```

Verify everything is ready:

```powershell
python .claude/skills/relight/scripts/preflight.py
```

Expect `READY`.

> **Symlink note:** Windows needs Developer Mode enabled (or an elevated shell) to create
> symlinks. If it can't, the installer copies the skill instead — in that case, re-run
> `install.ps1` after pulling updates to keep the user-level copy in sync.

## Usage

In Claude Code, just ask:

> Use the relight skill on `C:\path\clip.mp4` — put me in a three-point lighting setup with
> neon streamer lights in the background. Reference: `C:\path\ref.jpg`

The skill will extract the best frame, generate the relit still, **show it to you with the
cost**, and wait for your approval before running the paid video step. Output lands in
`relight-outputs/`.

## Cost

The Fal models are paid (only premium models pull this off). Rough figures:

| Step | Approx cost |
|---|---|
| Relit still (Nano Banana Pro, 2K) | ~$0.15 |
| Relit video (Kling O1) | ~$0.17 / second |

Examples: a 4.5s clip ≈ **$0.76**. A 24s clip ≈ 3 segments ≈ **~$4**. You always see the
estimate (and, for longer clips, the segment count) before anything is spent.

## Constraints

- Each video generation is one **3–10 second** segment. Clips ≤10s run in one pass; longer
  clips are auto-split and concatenated; clips under 3s are rejected.
- Input video must be **720–2160px** and **≤200MB** (per Kling O1).
- Best suited to **short-form** content unless you have budget for many segments.

## Project layout

```
.claude/skills/relight/    the skill (canonical source)
  SKILL.md                 orchestration Claude follows
  scripts/                 extract_frame, relight_image, relight_video,
                           split_video, concat_video, relight_batch, preflight
  tests/                   unit tests (run: python -m pytest .claude/skills/relight/tests)
  requirements.txt
  .env.example
install.ps1                one-step installer
```
