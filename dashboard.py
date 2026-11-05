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


def available_sources() -> list[str]:
    ensure_dirs()
    files = sorted(
        (p for p in INPUT.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if SEED.is_file():
        files.insert(0, SEED)
    return list(dict.fromkeys(str(p) for p in files))


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


def run_render(selected: str) -> Iterator[tuple[str, str, str]]:
    ensure_dirs()
    if not selected:
        yield "Select a source video first.", dashboard_status(), ""
        return
    source = Path(selected)
    if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
        yield "The selected source is no longer available. Refresh the list.", dashboard_status(), ""
        return
    command = [
        sys.executable, "studio.py",
        "--input", str(INPUT),
        "--output", str(OUTPUT),
        "--work", str(WORK),
        "--broll-dir", str(BROLL),
        "--seed-file", str(source),
    ]
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
                gr.Markdown("### Add a source video")
                upload = gr.File(label="Choose video from your device", file_types=["video"], type="filepath")
                gr.HTML("""
                <div id="hk-upload-progress" style="display:none;padding:14px;border:1px solid var(--border-color-primary);border-radius:12px;margin:8px 0;">
                  <div id="hk-upload-label" style="font-weight:600;margin-bottom:8px;">Waiting for upload…</div>
                  <div style="height:12px;background:var(--background-fill-secondary);border-radius:99px;overflow:hidden;">
                    <div id="hk-upload-bar" style="height:100%;width:0%;background:var(--button-primary-background-fill);transition:width .15s;"></div>
                  </div>
                  <div id="hk-upload-detail" style="font-size:13px;opacity:.8;margin-top:8px;">Transferred size, speed and estimated time will appear here.</div>
                </div>
                """)
                upload_button = gr.Button("Add to project", variant="secondary")
                upload_message = gr.Markdown()
                gr.Markdown("### Select a project video")
                source = gr.Dropdown(label="Source video", choices=available_sources(), interactive=True)
                refresh_button = gr.Button("Refresh source list")
                render_button = gr.Button("Run AI edit", variant="primary")
                logs = gr.Textbox(label="Processing log", lines=12, max_lines=24, interactive=False)
                render_preview = gr.Video(label="Latest rendered preview")
            with gr.Tab("Review & export"):
                gr.Markdown("### Rendered videos\nChoose an export to preview it. Quality reports and transcripts are saved in the same output folder in Google Drive.")
                output_choice = gr.Dropdown(label="Completed exports", choices=output_videos())
                output_refresh = gr.Button("Refresh exports")
                preview_button = gr.Button("Load preview")
                output_preview = gr.Video(label="Final review video")
                output_file = gr.File(label="Download selected MP4")
                qc_note = gr.Markdown("Always watch the full export and inspect its QC report before publishing.")
        upload_button.click(upload_video, inputs=upload, outputs=[source, upload_message])
        refresh_button.click(refresh_sources, outputs=[source, status])
        render_button.click(run_render, inputs=source, outputs=[logs, status, render_preview])
        output_refresh.click(refresh_outputs, outputs=[output_choice, status])
        preview_button.click(load_preview, inputs=output_choice, outputs=output_preview)
        output_choice.change(load_preview, inputs=output_choice, outputs=output_file)
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
