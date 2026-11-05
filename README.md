# HK AI Video Studio

A reusable, Drive-folder-based video processing worker for HK_blogspot. The repository is the source of truth for the editing engine; Google Drive holds source videos and rendered outputs.

## Current workflow

1. Put source videos in `MyDrive/HK_Video_Studio/INPUT`.
2. Start the Colab runner once for the active session.
3. The worker watches the folder and automatically processes newly added videos.
4. Finished review MP4s, transcripts, captions and QC reports are written to `OUTPUT/<video>_<job-id>/`.
5. Original files are never modified.

## Start the worker

Open `colab_runner.ipynb` in Google Colab and choose **Runtime → Run all**. Authorize Google Drive when prompted. Leave the notebook session running while uploads are being processed.

The notebook is a one-time session launcher, not a per-video editing checklist. During a running session, new videos are discovered automatically.

## Free-tier constraints

- Colab free sessions can disconnect, time out or be unavailable. A disconnected session cannot watch Drive until restarted.
- This worker uses local FFmpeg and Whisper transcription; it does not require a paid API.
- Large 4K videos can take significant time and temporary disk space.
- The current baseline automatically transcribes, detects long silence, creates captions, renders vertical 9:16 output and checks the export.
- Semantic best-take selection, face/gesture-aware reframing, AI-generated graphics and automatic B-roll sourcing are planned stages, not claims of the current baseline. The worker must not silently delete repeated dialogue just because transcript strings look similar.

## Folder layout

```
MyDrive/HK_Video_Studio/
  INPUT/
  OUTPUT/
```

## Safety

- Source videos are read-only.
- Each job gets its own output directory.
- Long silence is detected conservatively; short pauses are preserved.
- Review every rendered video before publishing.
- No API keys are needed for the baseline.

## Local development

Python 3.10+ and FFmpeg are required.

```bash
pip install -r requirements.txt
python studio.py --input ./INPUT --output ./OUTPUT --watch
```

The local watcher processes videos placed in the input directory. In Colab, Drive is mounted automatically by the notebook.


## AI Director foundation (in progress)

The current development branch adds two foundations for the next editing stages:

- **Persistent job tracking:** completed inputs are remembered in `OUTPUT/.job_state.json`, so restarting Colab does not automatically render the same unchanged source again. Failed jobs are recorded and can be retried with `--retry-failed`.
- **Editorial review suggestions:** `editorial_review.json` flags potentially repeated transcript lines for review. Similarity is not treated as proof of a bad take, so no speech is automatically removed by this detector.
- **Existing source support:** the Colab launcher passes the existing `HK_Video_Studio/Vid1.MP4` as a one-time seed input before continuing to watch `INPUT`.

These changes are an engineering foundation, not a claim that semantic editing, gesture understanding, or automatic B-roll is complete. GitHub Actions runs Python compile and unit checks on pushes and pull requests.


### AI Director (first implementation)

Each processed video now receives a `director_plan.json` alongside the transcript and quality report. When a Colab secret named `GEMINI_API_KEY` is available, the optional Gemini director reviews transcript context and proposes:
- a possible opening hook;
- topic sections;
- likely retakes and preferred takes for review;
- candidate removals requiring approval;
- B-roll ideas and caption emphasis.

The plan is index-validated before it is saved. No dialogue is automatically deleted. If the API key is missing, the provider is unavailable, or the response cannot be validated, the worker writes a conservative local fallback plan instead. Set `GEMINI_MODEL` to select a model available to your API key; the default is `gemini-2.0-flash`.


## Visual analysis and export QC (development branch)

The development branch samples frames with OpenCV to estimate frontal-face positions, exposure and candidate scene changes. It writes `visual_analysis.json`, including per-sample face-center estimates. When horizontal cropping is needed, the renderer interpolates smoothed face-center positions over the edited timeline and compensates for removed silence, rather than relying only on one static center. This is approximate sampled-frame tracking, not gesture, gaze, identity or emotion recognition; it may miss profiles, occlusion or rapid movement. Native 9:16 source footage naturally needs little or no horizontal reframing.

After rendering, deterministic checks validate the output video stream, audio stream, expected 1080x1920 resolution, positive duration, non-empty file, full FFmpeg decode integrity and SRT cue structure/timing. Final audio is loudness-normalized to a consistent target. Results are written to `qc_report.json`; a failed export check marks the job as failed rather than silently accepting a broken output. These checks do not replace a human visual/audio review.


### Styled captions and stricter checks

The renderer now burns an ASS caption track into the final MP4. Captions use bold white text with a dark outline; keywords explicitly selected by the AI Director are highlighted in yellow. The SRT sidecar remains available for review and is independently checked for malformed, overlapping, empty or missing cues. The export is marked failed if the video stream, audio stream, expected portrait resolution, duration, file size or caption track fails validation.


### Director-triggered smart punch-ins (development branch)

When the AI Director returns validated opening-hook segment indexes, the renderer now applies a subtle 6% punch-in over those moments. The zoom ramps in and out smoothly, and its timing is remapped after long-silence removal. If the Director is unavailable or does not identify a hook, the expression stays at native 1x scale. Invalid indexes are ignored; the zoom strength is bounded. This is a restrained emphasis effect, not gesture-aware camera direction, and it does not add B-roll or graphics.
