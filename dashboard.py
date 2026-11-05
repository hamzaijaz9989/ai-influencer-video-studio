#!/usr/bin/env python3
"""Browser dashboard for HK AI Video Studio (runs beside the engine in Colab)."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import gradio as gr

ROOT = Path(os.environ.get("HK_STUDIO_ROOT", "/content/drive/MyDrive/HK_Video_Studio"))
INPUT = ROOT / "INPUT"
OUTPUT = ROOT / "OUTPUT"
BROLL = ROOT / "BROLL"
WORK = Path("/content/hk_video_work")
SEED = ROOT / "Vid1.MP4"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".avi"}

UPLOAD_PROGRESS_JS = r"""
() => {
  if (window.__hkUploadProgressInstalled) return;
  window.__hkUploadProgressInstalled = true;
  const fmt = (n) => n >= 1024 ** 3 ? (n / 1024 ** 3).toFixed(2) + " GB" : (n / 1024 ** 2).toFixed(1) + " MB";
  const update = (state, loaded, total, started) => {
    const panel = document.getElementById("hk-upload-progress");
    if (!panel) return;
    panel.style.display = "block";
    const label = panel.querySelector("#hk-upload-label");
    const detail = panel.querySelector("#hk-upload-detail");
    const bar = panel.querySelector("#hk-upload-bar");
    const pct = total > 0 ? Math.min(100, loaded / total * 100) : 0;
    bar.style.width = pct.toFixed(1) + "%";
    label.textContent = state === "done" ? "Transfer complete — now click Add to project" :
      state === "error" ? "Upload failed — check your connection and try again" :
      "Uploading video… " + pct.toFixed(1) + "%";
    if (state === "done") detail.textContent = fmt(total) + " transferred. The file is ready to add to the project.";
    else if (state === "error") detail.textContent = fmt(loaded) + " transferred before the connection failed.";
    else {
      const seconds = Math.max(1, (Date.now() - started) / 1000);
      const speed = loaded / seconds;
      const remaining = speed > 0 && total > loaded ? Math.ceil((total - loaded) / speed) : 0;
      detail.textContent = fmt(loaded) + " of " + fmt(total) + " · " +
        fmt(speed) + "/s · " + (remaining ? "about " + Math.floor(remaining / 60) + "m " + (remaining % 60) + "s remaining" : "calculating time");
    }
  };
  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this.__hkUploadRequest = typeof url === "string" && url.includes("/upload");
    return originalOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(body) {
    if (this.__hkUploadRequest && body instanceof FormData && this.upload) {
      const started = Date.now();
      this.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) update("uploading", event.loaded, event.total, started);
      });
      this.addEventListener("load", () => {
        if (this.status >= 200 && this.status < 300) update("done", 1, 1, started);
        else update("error", 0, 1, started);
      });
      this.addEventListener("error", () => update("error", 0, 1, started));
      this.addEventListener("abort", () => update("error", 0, 1, started));
    }
    return originalSend.apply(this, arguments);
  };
}
"""


def ensure_dirs() -> None:
    for path in (INPUT, OUTPUT, BROLL, WORK):
        path.mkdir(parents=True, exist_ok=True)


def _is_video_file(path: Path) -> bool:
    try:
        return path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    except OSError:
        return False


def available_drive_videos() -> list[str]:
    """List actual video files in the configured mounted Drive project folder."""
    ensure_dirs()
    excluded = {OUTPUT.resolve(), BROLL.resolve()}
    files: list[Path] = []
    # Include the known source explicitly; recursive Drive scans can occasionally
    # fail on transient/permission errors in unrelated folders.
    if _is_video_file(SEED):
        files.append(SEED)
    try:
        for path in ROOT.rglob("*"):
            try:
                if not _is_video_file(path):
                    continue
                resolved = path.resolve()
                if any(parent == resolved or parent in resolved.parents for parent in excluded):
                    continue
                files.append(path)
            except OSError:
                continue
    except OSError:
        pass
    unique = {str(path.resolve()) for path in files if _is_video_file(path)}
    return sorted(unique, key=lambda value: Path(value).stat().st_mtime, reverse=True)


def available_sources() -> list[str]:
    """List only real video files from INPUT and the mounted Drive project folder."""
    ensure_dirs()
    files: list[str] = []
    try:
        files.extend(
            str(p.resolve()) for p in INPUT.iterdir()
            if _is_video_file(p)
        )
    except OSError:
        pass
    files.extend(available_drive_videos())
    return sorted(set(files), key=lambda value: Path(value).stat().st_mtime, reverse=True)


def drive_diagnostics(count: int | None = None) -> str:
    mounted = Path("/content/drive/MyDrive")
    root_exists = ROOT.is_dir()
    seed_exists = _is_video_file(SEED)
    details = [
        f"Drive mounted: **{'Yes' if mounted.is_dir() else 'No'}**",
        f"Project folder: `{ROOT}` — **{'found' if root_exists else 'not found'}**",
        f"Known source Vid1.MP4: **{'found' if seed_exists else 'not found'}**",
    ]
    if count is not None:
        details.append(f"Video files found: **{count}**")
    return "  ·  ".join(details)


def select_drive_video(selected: str | None) -> tuple[gr.Dropdown, str]:
    if not selected:
        return gr.update(choices=available_sources()), "Choose a video from your Google Drive folder."
    path = Path(selected).resolve()
    root = ROOT.resolve()
    if root not in path.parents or not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        return gr.update(choices=available_sources()), "That Drive file is unavailable. Refresh the Drive list."
    choices = available_sources()
    if str(path) not in choices:
        choices.insert(0, str(path))
    return gr.update(choices=choices, value=str(path)), f"Selected **{path.name}** directly from Google Drive. No re-upload needed."


def refresh_drive_videos() -> tuple[gr.Dropdown, str]:
    videos = available_drive_videos()
    message = drive_diagnostics(len(videos))
    if videos:
        message += "\\n\\nSelect a file and tap **Use selected Drive video**. No device upload is needed."
    else:
        message += "\\n\\nNo video files were detected. Confirm Drive is mounted and the video is inside the configured project folder."
    return gr.update(choices=videos, value=videos[0] if videos else None), message


def output_videos() -> list[str]:
    ensure_dirs()
    return sorted(
        (str(p) for p in OUTPUT.glob("*/FINAL_REVIEW.mp4") if p.is_file()),
        key=lambda value: Path(value).stat().st_mtime,
        reverse=True,
    )


def dashboard_status() -> str:
    ensure_dirs()
    state_path = OUTPUT / ".job_state.json"
    if not state_path.exists():
        return "No processing history yet."
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        jobs = data.get("jobs", {})
        counts = {"completed": 0, "failed": 0, "processing": 0}
        for item in jobs.values():
            status = item.get("status")
            if status in counts:
                counts[status] += 1
        return (
            f"**Jobs:** {len(jobs)}  ·  "
            f"**Completed:** {counts['completed']}  ·  "
            f"**Failed:** {counts['failed']}  ·  "
            f"**Processing:** {counts['processing']}"
        )
    except Exception as exc:
        return f"Could not read job status: {exc}"


def upload_video(uploaded: str | None) -> tuple[gr.Dropdown, str]:
    ensure_dirs()
    if not uploaded:
        return gr.update(choices=available_sources()), "Choose a video file first."
    source = Path(uploaded)
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        return gr.update(choices=available_sources()), "Unsupported file type. Choose a video."
    destination = INPUT / source.name
    if source.resolve() != destination.resolve():
        if destination.exists():
            return gr.update(choices=available_sources()), f"{source.name} already exists in INPUT."
        shutil.copy2(source, destination)
    choices = available_sources()
    return gr.update(choices=choices, value=str(destination)), f"Added **{source.name}** to the project INPUT folder."


def refresh_sources() -> tuple[gr.Dropdown, str]:
    choices = available_sources()
    return gr.update(choices=choices, value=choices[0] if choices else None), dashboard_status()


def run_render(selected: str, creative_prompt: str = "") -> Iterator[tuple[str, str, str]]:
    ensure_dirs()
    if not selected:
        yield "Select a video file from the Drive list or project source list first.", dashboard_status(), ""
        return
    source = Path(selected).expanduser()
    try:
        source = source.resolve(strict=True)
    except (OSError, RuntimeError):
        yield f"Selected path does not exist: {selected}. Refresh the Drive list and choose a video file.", dashboard_status(), ""
        return
    if not source.is_file():
        yield f"The selected path is a folder, not a video file: {source}. Choose an MP4/MOV video from the list.", dashboard_status(), ""
        return
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        yield f"Unsupported source type: {source.suffix or '(no extension)'}. Choose an MP4/MOV video.", dashboard_status(), ""
        return
    command = [
        sys.executable, "studio.py",
        "--input", str(INPUT),
        "--output", str(OUTPUT),
        "--work", str(WORK),
        "--broll-dir", str(BROLL),
        "--seed-file", str(source),
    ]
    if creative_prompt and creative_prompt.strip():
        prompt_file = WORK / "creative_direction.txt"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(creative_prompt.strip(), encoding="utf-8")
        command.extend(["--creative-prompt-file", str(prompt_file)])
    yield f"Starting **{source.name}**… This may take a while for 4K footage.", dashboard_status(), ""
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        lines.append(line.rstrip())
        yield "\n".join(lines[-100:]), dashboard_status(), ""
    code = process.wait()
    videos = output_videos()
    preview = videos[0] if videos else ""
    if code == 0:
        yield "\n".join(lines[-100:]) + "\n\nProcessing finished. Review the export before publishing.", dashboard_status(), preview
    else:
        yield "\n".join(lines[-100:]) + f"\n\nProcessing stopped with exit code {code}. Check the error log in OUTPUT.", dashboard_status(), preview


def enhance_selected_video(selected: str, strength: str, denoise: bool) -> tuple[str, str]:
    """Run the standalone enhancer without invoking transcription or editing."""
    ensure_dirs()
    if not selected:
        return "Choose a video first.", ""
    source = Path(selected).expanduser()
    try:
        source = source.resolve(strict=True)
        if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
            return "The selected source is not a supported video file.", ""
        from studio_core.enhancer import enhance_video
        destination = OUTPUT / "ENHANCED" / f"{source.stem}_enhanced.mp4"
        if destination.exists():
            destination = OUTPUT / "ENHANCED" / f"{source.stem}_enhanced_{secrets.token_hex(3)}.mp4"
        result = enhance_video(source, destination, strength=strength, denoise=denoise)
        return f"Enhancement complete. Original preserved. Output: **{result.name}**", str(result)
    except Exception as exc:
        return f"Enhancement failed: {exc}", ""


def save_edit_feedback(selected: str, rating: str, note: str = "") -> str:
    """Persist simple human feedback for the next editing session."""
    if not selected:
        return "Choose a completed export before submitting feedback."
    path = Path(selected).expanduser().resolve()
    try:
        path.relative_to(OUTPUT.resolve())
    except ValueError:
        return "Feedback can only be attached to an export inside this project's OUTPUT folder."
    if not path.is_file() or path.name != "FINAL_REVIEW.mp4":
        return "Select a valid completed review export."
    from studio_core.self_improvement import record_feedback, profile_summary
    profile = record_feedback(OUTPUT / ".learning_profile.json", rating, note)
    feedback_path = path.parent / "user_feedback.json"
    feedback_path.write_text(json.dumps({
        "rating": rating,
        "note": note[:500],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return "Feedback saved. " + profile_summary(profile)


def refresh_outputs() -> tuple[gr.Dropdown, str]:
    videos = output_videos()
    return gr.update(choices=videos, value=videos[0] if videos else None), dashboard_status()


def load_preview(path: str | None) -> str | None:
    return path or None


def build_app() -> gr.Blocks:
    css = """
    .gradio-container {max-width: 1180px !important; margin: auto !important;}
    #hero {padding: 22px 24px; border: 1px solid var(--border-color-primary); border-radius: 18px;}
    #hero h1 {margin-bottom: 4px;}
    .muted {opacity: .72;}
    """
    with gr.Blocks(title="HK AI Video Studio", theme=gr.themes.Soft(), css=css, js=UPLOAD_PROGRESS_JS) as app:
        with gr.Column(elem_id="hero"):
            gr.Markdown("# HK AI Video Studio\nYour AI-assisted editing workspace. Upload, process, review and export creator videos.")
            status = gr.Markdown(dashboard_status())
        with gr.Tabs():
            with gr.Tab("Projects"):
                gr.Markdown("## Step 1 — Choose your video")
                gr.Markdown(
                    "Your video must already be inside **Google Drive → MyDrive → HK_Video_Studio**. "
                    "Choose it below. You do **not** need to upload it again."
                )
                drive_videos = available_drive_videos()
                drive_video = gr.Dropdown(
                    label="Your Google Drive videos",
                    choices=drive_videos,
                    value=drive_videos[0] if drive_videos else None,
                    interactive=True,
                )
                with gr.Row():
                    drive_refresh = gr.Button("Refresh video list", variant="secondary")
                    drive_select = gr.Button("Use this video", variant="primary")
                drive_message = gr.Markdown(
                    drive_diagnostics(len(drive_videos))
                    + "\\n\\nChoose a video above, then tap **Use this video**."
                )

                gr.Markdown("## Step 2 — Check your selected video")
                initial_sources = available_sources()
                source = gr.Dropdown(
                    label="Video ready to edit",
                    choices=initial_sources,
                    value=initial_sources[0] if initial_sources else None,
                    interactive=True,
                )
                source_refresh = gr.Button("Refresh selected video list", variant="secondary")
                gr.Markdown("## Optional — Add your creative direction")
                creative_prompt = gr.Textbox(
                    label="What creative ideas should the AI add?",
                    placeholder="Example: Make the words LEVEL UP orbit around the speaker's neck, follow their movement, and stay clear of their face.",
                    lines=4,
                    max_lines=10,
                )
                gr.Markdown("Leave this empty for normal automatic editing. Your instructions are added on top of the automatic edit.")
                render_button = gr.Button("Start AI editing", variant="primary", size="lg")
                logs = gr.Textbox(
                    label="Editing progress",
                    lines=8,
                    max_lines=18,
                    interactive=False,
                    placeholder="Progress messages will appear here after you start editing.",
                )
                render_preview = gr.Video(label="Your edited video")

                with gr.Accordion("Need to upload a video from your phone instead?", open=False):
                    gr.Markdown(
                        "Only use this if the video is **not already in Google Drive**. "
                        "Large videos may take a long time to upload."
                    )
                    upload = gr.File(
                        label="Choose a video from this phone",
                        file_types=["video"],
                        type="filepath",
                    )
                    upload_button = gr.Button("Add phone video to project", variant="secondary")
                    upload_message = gr.Markdown()

            with gr.Tab("Video Enhancer"):
                gr.Markdown("## Enhance any video independently")
                gr.Markdown("Works with supported MP4, MOV, MKV, M4V, AVI and WebM files. Preserves the original aspect ratio, resolution, frame rate and audio; exports a new enhanced MP4. It does not run captions, silence removal or influencer editing.")
                enhancer_source = gr.Dropdown(
                    label="Choose any source video",
                    choices=available_sources(),
                    value=None,
                    interactive=True,
                )
                enhancer_refresh = gr.Button("Refresh video list", variant="secondary")
                enhancer_strength = gr.Radio(
                    choices=["light", "balanced", "strong"],
                    value="balanced",
                    label="Enhancement strength",
                )
                enhancer_denoise = gr.Checkbox(value=True, label="Reduce visible noise")
                enhancer_button = gr.Button("Enhance video", variant="primary", size="lg")
                enhancer_status = gr.Markdown()
                enhancer_preview = gr.Video(label="Enhanced video preview")

            with gr.Tab("Review & export"):
                gr.Markdown("### Rendered videos\nChoose an export to preview it. Quality reports and transcripts are saved in the same output folder in Google Drive.")
                output_choice = gr.Dropdown(label="Completed exports", choices=output_videos())
                output_refresh = gr.Button("Refresh exports")
                preview_button = gr.Button("Load preview")
                output_preview = gr.Video(label="Final review video")
                output_file = gr.File(label="Download selected MP4")
                qc_note = gr.Markdown("Always watch the full export and inspect its QC report before publishing.")
                gr.Markdown("### Help the editor improve")
                feedback_rating = gr.Radio(
                    choices=[("Better — I like this edit", "better"), ("About right", "same"), ("Worse — needs improvement", "worse")],
                    value="same",
                    label="How did this edit turn out?",
                )
                feedback_note = gr.Textbox(
                    label="Optional feedback",
                    placeholder="Example: less zoom, cleaner captions, keep more pauses, warmer color.",
                    lines=2,
                    max_lines=4,
                )
                feedback_button = gr.Button("Save feedback for future edits", variant="primary")
                feedback_status = gr.Markdown()

        enhancer_refresh.click(refresh_sources, outputs=[enhancer_source, status])
        enhancer_button.click(enhance_selected_video, inputs=[enhancer_source, enhancer_strength, enhancer_denoise], outputs=[enhancer_status, enhancer_preview])
        drive_refresh.click(refresh_drive_videos, outputs=[drive_video, drive_message])
        drive_select.click(select_drive_video, inputs=drive_video, outputs=[source, drive_message])
        upload_button.click(upload_video, inputs=upload, outputs=[source, upload_message])
        source_refresh.click(refresh_sources, outputs=[source, status])
        render_button.click(run_render, inputs=[source, creative_prompt], outputs=[logs, status, render_preview])
        output_refresh.click(refresh_outputs, outputs=[output_choice, status])
        preview_button.click(load_preview, inputs=output_choice, outputs=output_preview)
        output_choice.change(load_preview, inputs=output_choice, outputs=output_file)
        feedback_button.click(save_edit_feedback, inputs=[output_choice, feedback_rating, feedback_note], outputs=feedback_status)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--share", action="store_true", help="Create a temporary public Gradio link for this Colab session.")
    parser.add_argument("--server-port", type=int, default=7860)
    args = parser.parse_args()
    ensure_dirs()
    app = build_app()
    username = "hkstudio"
    password = secrets.token_urlsafe(18)
    print("Dashboard login username: " + username, flush=True)
    print("Dashboard login password: " + password, flush=True)
    print("Dashboard starting. Keep this Colab session active while using its link.", flush=True)
    app.queue(max_size=4).launch(
        server_name="0.0.0.0",
        server_port=args.server_port,
        share=args.share,
        auth=(username, password),
        show_error=True,
    )


if __name__ == "__main__":
    main()
