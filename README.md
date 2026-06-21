# Relight & MediaGen — AI video and image tools you run by just talking

This is a pair of tools that turn plain requests into finished images and video — all from
inside **Claude Code** (the AI assistant on your computer). You don't edit anything by hand and
you don't run any commands. You describe what you want, Claude does it, and you approve the cost
before anything is spent.

There are two tools in here:

### 🎬 Relight — fix the lighting and background of your talking-head videos
Got a clip where the lighting is flat or the background is messy? Relight drops you into a
clean, professional, cinematic setting and makes you look warm and well-lit — while keeping
your face, your movements, and your voice exactly the same. Long videos are handled
automatically.

> *Example:* "Relight this clip of me — put me in a cozy home office with soft lighting."

### 🖼️ MediaGen — make and edit images and video from a description
- **Make an image** from a description ("a husky astronaut on Mars, cinematic").
- **Edit a photo** using another photo as a reference (swap an outfit, change a background — your subject stays recognizable).
- **Turn a photo into a short video** (a still image starts gently moving).
- **Sharpen a blurry or low-quality video** (make it crisp and higher-resolution).

> *Example:* "Make an image of a golden retriever in a superhero costume," then
> "now turn that into a short video," then "make it sharper."

**You never have to know which AI model to use.** Just say what you want — the tool quietly
picks the best one for the job.

---

## ✨ The easiest way to start

1. Open this folder in **Claude Code**.
2. Type this and press enter:

> **"Read the README and set these tools up for me."**

That's it. Claude will install everything, ask you for one key (explained below), check that
it all works, and then tell you it's ready. **You won't need to type any commands yourself.**

---

## What you'll need

- **Claude Code** — the AI assistant app these tools live inside. (They won't work in the
  regular Claude website or app, because they need to save files to your computer.)
- **A Fal account with a few dollars on it.** "Fal" is the service that actually does the
  image and video generating. It's pay-as-you-go — there's no monthly fee, you just pay a few
  cents per image or a small amount per video. You'll create a free account at
  **https://fal.ai/dashboard/keys**, add maybe $10–20, and copy your "API key" (a long
  password-like code). Claude will tell you exactly where to put it. **$10–20 lasts a long
  time** for occasional use.
- A **Windows** computer.

When Claude asks for your Fal key, you can paste it to Claude and it will save it in the right
place for you — or, if you'd rather, Claude will tell you which file to paste it into yourself.
You only do this once, and the same key powers both tools.

---

## What it costs

These tools use premium AI, so each generation costs a little real money — but it's small, and
**you always see the price and approve it before anything is charged.**

| What you're making | Roughly costs |
|---|---|
| An image | about 15¢ (a bit more for ultra-high-res) |
| A few seconds of video | under $1 |
| Sharpening/upscaling a short video | a few cents to ~50¢ |
| Relighting a short talking-head clip | usually under $1; longer clips cost a bit more |

For anything that costs more than pennies (videos, upscaling, relighting), Claude shows you the
estimated price and waits for you to say "go" before spending. Nothing is charged without your
okay.

---

## Things you can say once it's set up

Just talk to Claude naturally. For example:

**Relight:**
> "Relight this video: `C:\Users\me\Videos\myclip.mp4`. Put me in a modern studio with warm
> lighting. Here's the look I want: `C:\Users\me\Pictures\reference.jpg`"

**MediaGen:**
> "Generate an image of a vintage red sports car on a coastal road at sunset."
>
> "Edit this photo so the person is wearing a tuxedo — keep their face the same: `C:\...\photo.jpg`"
>
> "Turn this image into a 4-second video: `C:\...\image.png`"
>
> "Make this video sharper: `C:\...\clip.mp4`"

**Tip:** when you point to a file, give its full location. On Windows you can right-click a
file and choose **"Copy as path,"** then paste that.

---

## Where your finished files go

- Relit videos land in a `relight-outputs` folder, each in its own subfolder named after your clip.
- Images and videos from MediaGen land in a `mediagen-outputs` folder.

Claude tells you the exact location each time.

---

## A note on safety and privacy

- Your Fal key is saved in a private file on your computer and is **never** shared, posted, or
  put online. (It's kept out of any backups of this project.)
- Your videos and images are sent to Fal to be processed (that's how the AI works), and the
  finished results come back to your computer.
- Nothing costs money without you approving it first.

---

<details>
<summary><b>⚙️ For Claude Code — automated setup steps (you, the human, can skip this part)</b></summary>

**This section is instructions for Claude, not for you.** When the user says "read the README
and set these up," do the following in order, then confirm readiness — do not skip the
verification.

This repo ships **two** skills — **Relight** and **MediaGen** — on a shared Fal core
(`falkit`) and **one shared key**. `install.ps1` sets up both at once.

1. **Run the installer.** On Windows: `./install.ps1`. It installs ffmpeg (via winget), the
   editable shared core (`pip install -e ./falkit-core`), both skills' Python deps, links
   `~/.claude/skills/relight` and `~/.claude/skills/mediagen`, seeds the shared key file
   `~/.claude/fal.env`, and verifies `import falkit` succeeds.
   - On macOS/Linux (no `install.ps1`): install ffmpeg (`brew install ffmpeg` /
     `apt install ffmpeg`), `pip install -e ./falkit-core`, then
     `pip install -r .claude/skills/mediagen/requirements.txt` and
     `-r .claude/skills/relight/requirements.txt`, and copy `fal.env.example` to
     `~/.claude/fal.env`.
   - **ffmpeg PATH gotcha:** winget often updates PATH but the current shell won't see it until
     restarted. If `ffmpeg`/`ffprobe` aren't found right after install, locate the binary (e.g.
     under `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\...\bin`) and prepend that dir
     to PATH for your commands, or tell the user to restart the shell.

2. **Get the Fal API key from the user.** Ask them to paste their key (from
   https://fal.ai/dashboard/keys — pay-per-use, so they need a little credit). Write it into
   `~/.claude/fal.env` as `FAL_KEY=<their key>` using a file edit — **do not echo the key back
   into the chat.** This one key serves BOTH skills. It is gitignored; never commit it. If they'd
   rather not paste it, tell them to edit that file themselves.

3. **Verify the environment.** Run `python .claude/skills/relight/scripts/preflight.py`. Expect
   `READY`. If any line shows `[XX]`, fix it (install the missing dep, fix the PATH, or get the
   key) and re-run until it reports `READY`. This also confirms the shared key resolves.

4. **Confirm and hand off.** Tell the user setup is complete and ask what they want to do —
   **Relight** a talking-head video, or use **MediaGen** to generate/edit an image, animate a
   still, or upscale a video. Then follow that skill's `SKILL.md` (each has its own cost
   approval gates before any paid step).

> Orchestration guides: `.claude/skills/relight/SKILL.md` and
> `.claude/skills/mediagen/SKILL.md`. Shared Fal plumbing lives in `falkit-core/`. Inspired by
> the [Systems by Vic](https://www.youtube.com/watch?v=pZNQwzW_JjM) Relight & MediaGen videos.

</details>
