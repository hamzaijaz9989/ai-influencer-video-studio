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
