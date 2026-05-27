# 03 — Video/Audio Transcripts: Whisper, yt-dlp, ffmpeg-python

**Status:** Research Complete | **Owner:** Mnemosyne Python Satellite Layer
**Last Updated:** 2026-05-27

---

## Executive Summary

Audio and video transcription is a domain where Python-native tooling dominates so completely that Rust is not even a participant in the conversation. OpenAI's **Whisper** family (via `openai-whisper`, `faster-whisper`, and `whisperx`) is the de facto standard for local speech-to-text. **yt-dlp** is the battle-tested tool for extracting audio streams and metadata from 1,700+ video platforms. **ffmpeg** (wrapped via `ffmpeg-python` or called via subprocess) is the universal audio/video preprocessor. Together, these three form a pipeline that the Rust core cannot replicate without spawning a Python satellite.

This document breaks down model selection, accuracy benchmarks, speed tradeoffs, speaker diarization, preprocessing chains, metadata extraction, and integration fit for Mnemosyne's ingestion engine.

---

## 1. The Rust Landscape: Nonexistent

| Approach | Maturity | Transcription | Diarization | Preprocessing | Verdict |
|---|---|---|---|---|---|
| `whisper-rs` (bindings) | Experimental | Via `whisper.cpp` GGML | None | None | Bindings lag; no diarization |
| Pure Rust ASR | None | None | None | None | No equivalent ecosystem |
| Rust FFmpeg wrappers | Mature | N/A (decoding only) | N/A | Good (`ffmpeg-next`) | Can decode; cannot transcribe |

**The structural problem:** Speech recognition at Whisper's quality requires 1.5B-parameter transformer models, VAD (voice activity detection), forced alignment, and speaker embedding models. The Python ecosystem has 3+ years of production refinement in this stack. Rust has `whisper.cpp` bindings (`whisper-rs`) but they lack the higher-level orchestration (batching, diarization, alignment) that makes Whisper production-ready.

> **Mnemosyne Decision:** Python satellite for all audio/video transcription and preprocessing. No Rust-native transcription in Phase 1.

---

## 2. Whisper: The Transcription Engine

### 2.1 Model Family Overview

Whisper comes in 7 sizes, from Tiny (39M parameters) to Large-v3 (1.5B). Accuracy and speed trade off dramatically. For Mnemosyne's Foundry node (batch processing, GPU-available), the choice is between **Large-v3** (best accuracy) and **Large-v3 Turbo** (distilled, 8x faster, slight accuracy loss).

| Model | Parameters | English WER (clean) | Real-time Factor | VRAM | Use Case |
|---|---|---|---|---|---|
| Tiny | 39M | ~10-15% | 32x | ~273 MB | Draft, constrained devices |
| Base | 74M | ~8-12% | 16x | ~500 MB | Mobile apps |
| Small | 244M | ~6-9% | 6x | ~1.2 GB | Balanced |
| Medium | 769M | ~4-6% | 2x | ~2.5 GB | Quality focused |
| Large-v2 | 1.5B | ~3-5% | 1x | ~3.9 GB | Production (older) |
| Large-v3 | 1.5B | ~2.7% | 1x | ~3.9 GB | **Production (current best)** |
| Large-v3 Turbo | 809M | ~3-4% | 8x | ~2.0 GB | **Fast production (recommended)** |

**Real-world English WER** (meetings, calls, podcasts): 8-12% for Large-v3. This matches or beats most commercial APIs (Google Chirp ~8-11%, AWS Transcribe ~9-13%, Deepgram Nova-2 ~8-11%).

### 2.2 `openai-whisper` vs `faster-whisper` vs `whisperx`

| Feature | `openai-whisper` | `faster-whisper` | `whisperx` |
|---|---|---|---|
| **Backend** | PyTorch | CTranslate2 | CTranslate2 + wav2vec2 + pyannote |
| **Speed** | Baseline | **4x faster** | ~3x faster (with alignment) |
| **Accuracy** | Reference | Same | Same + better timestamps |
| **Word-level timestamps** | Segment-level (~1s drift) | Segment-level | **<100ms via forced alignment** |
| **Speaker diarization** | None | None | **pyannote.audio 3.1** |
| **Batching** | No | Yes | VAD-based batched inference |
| **Languages** | 99 | 99 | 99 + alignment for major languages |
| **License** | MIT | MIT | Apache-2.0 |
| **Best for** | Quick testing | Production throughput | **Production + diarization + subtitles** |

**`faster-whisper`** (SYSTRAN/CTranslate2) is the production default. It runs the same models at 4x speed with lower memory, supports INT8 quantization for CPU fallback, and integrates cleanly into pipelines.

**`whisperx`** adds two critical capabilities on top of `faster-whisper`:
1. **Forced phoneme alignment** via wav2vec2 — maps each word to its precise audio position (<100ms accuracy vs Whisper's ~1s drift). Essential for subtitle generation and precise provenance.
2. **Speaker diarization** via pyannote.audio 3.1 — identifies 'who said what when.' Accuracy: 90-95% for 2-3 clean speakers, 80-88% for 4-6 speakers, 70-80% for crowded meetings with crosstalk.

### 2.3 Whisper Limitations (Production Reality)

| Limitation | Impact | Mitigation |
|---|---|---|
| **No custom vocabulary boosting** | Mis-transcribes proper nouns, jargon, technical terms | Post-process with domain-specific replacement lists; or fine-tune on domain corpus |
| **Hallucinates on silence** | Invents text during long pauses (known in Large-v3) | VAD preprocessing to skip silent sections |
| **Poor on music + speech** | Hallucinates lyrics when music overlays speech | Pre-separate audio with Demucs or Spleeter |
| **Repeated tokens on loops** | Can get stuck repeating phrases | Less frequent in v3; use VAD segmentation |
| **Language detection errors** | Misidentifies similar languages (Ukrainian as Russian) | Specify `--language` explicitly for reliability |
| **2GB file size limit** | Very long files (>2 hours) should be chunked | Split at silence boundaries before transcription |
| **Real-time streaming not native** | Designed for batch transcription | For live: chunk with overlap; for archive: batch |

### 2.4 Mnemosyne Recommendation: `whisperx` as Default

For Mnemosyne's ingestion pipeline, `whisperx` is the clear choice because:
- **Provenance demands word-level timestamps** — the `pages` table's `provenance` field needs precise `line_start`/`line_end` equivalents in temporal form.
- **Multi-speaker content is common** — podcasts, interviews, lectures, meetings all benefit from speaker labels.
- **Subtitle export is a future feature** — WhisperX's SRT/VTT outputters are production-ready.
- **Apache-2.0 license** — fully compatible with Mnemosyne's MIT-bound code.

**Fallback:** `faster-whisper` for simple single-speaker content where diarization and alignment overhead are unnecessary.

---

## 3. yt-dlp: The Audio/Metadata Extractor

### 3.1 What yt-dlp Does

`yt-dlp` is an actively maintained fork of `youtube-dl` that downloads video and audio from **1,700+ websites**. For Mnemosyne, its value is not downloading videos for consumption — it is **extracting audio streams and rich metadata** for transcription and provenance.

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **Platform coverage** | YouTube, Vimeo, TikTok, Twitter/X, Instagram, Reddit, podcasts, lecture sites, 1,700+ extractors |
| **Audio extraction** | `-x --audio-format wav` extracts audio without re-encoding where possible |
| **Metadata extraction** | `--dump-json` returns structured metadata: title, description, uploader, duration, view_count, like_count, upload_date, tags, categories, chapters, subtitles |
| **Subtitle download** | `--write-auto-subs --sub-langs en` downloads auto-generated or manual captions |
| **Playlist/channel** | `--flat-playlist` for bulk metadata without downloading |
| **Format selection** | `-f 'bestaudio[ext=webm]/bestaudio'` for optimal audio quality |
| **Cookie support** | `--cookies cookies.txt` for authenticated/private content |
| **Proxy support** | `--proxy` for geo-restricted content |
| **License** | Unlicense (public domain) |

### 3.2 Metadata Extraction for Provenance

```python
import yt_dlp
import json

def extract_metadata(url: str) -> dict:
    opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': False,
        'writeinfojson': False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            'id': info.get('id'),
            'title': info.get('title'),
            'description': info.get('description'),
            'uploader': info.get('uploader'),
            'channel': info.get('channel'),
            'upload_date': info.get('upload_date'),
            'duration': info.get('duration'),
            'view_count': info.get('view_count'),
            'like_count': info.get('like_count'),
            'comment_count': info.get('comment_count'),
            'tags': info.get('tags', []),
            'categories': info.get('categories', []),
            'chapters': info.get('chapters', []),
            'thumbnail': info.get('thumbnail'),
            'webpage_url': info.get('webpage_url'),
            'extractor': info.get('extractor'),
            'formats_count': len(info.get('formats', [])),
        }
```

### 3.3 Audio Extraction Pipeline

```python
import yt_dlp

def extract_audio(url: str, output_path: str) -> str:
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '0',  # lossless where possible
        }],
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return f'{output_path}.wav'
```

### 3.4 yt-dlp 2026 Reality: PO Tokens and Bot Checks

YouTube's anti-bot stack tightened significantly between 2024-2026. Three changes affect Mnemosyne:

1. **PO tokens (Proof of Origin)** now gate many streaming endpoints. Without a valid token, you get degraded responses or 403s.
2. **Visitor data cookies** are required for most video page loads. Fresh IPs without warmed-up `__Secure-3PSID` hit consent walls.
3. **Datacenter IP flagging** — aggressive blocking of known datacenter ranges.

**Mitigation for Mnemosyne:**
- Use `--cookies cookies.txt` from a real browser session for authenticated extraction.
- Use `--extractor-args youtube:player_client=web` to avoid PO-token-gated endpoints where possible.
- For Foundry node behind residential IP: no issue. For cloud deployment: proxy rotation required.
- Keep yt-dlp updated weekly — extractors break frequently.

---

## 4. ffmpeg: The Universal Preprocessor

### 4.1 Role in the Pipeline

`ffmpeg` is the Swiss Army knife of audio/video processing. In Mnemosyne's transcription pipeline, it handles:

| Task | ffmpeg Command | Purpose |
|---|---|---|
| **Audio extraction** | `ffmpeg -i video.mp4 -vn -ar 16000 -ac 1 audio.wav` | Convert any video to 16kHz mono WAV (Whisper's preferred input) |
| **Format conversion** | `ffmpeg -i input.m4a -ar 16000 -ac 1 output.wav` | Normalize any audio format to Whisper-ready WAV |
| **Segmentation** | `ffmpeg -i long.mp3 -f segment -segment_time 1800 -c copy part%03d.mp3` | Split >2hr files into 30min chunks |
| **VAD pre-processing** | `ffmpeg -i input.wav -af silencedetect=noise=-50dB:d=2 -f null -` | Detect silence boundaries for chunking |
| **Noise reduction** | `ffmpeg -i noisy.wav -af 'highpass=f=200,lowpass=f=3000' clean.wav` | Basic filtering before transcription |
| **Volume normalization** | `ffmpeg -i input.wav -af loudnorm output.wav` | Normalize loudness for consistent transcription |
| **Subtitle burn-in** | `ffmpeg -i video.mp4 -vf subtitles=transcript.srt output.mp4` | For review/audit visualization |

### 4.2 Python Integration: `ffmpeg-python` vs Subprocess

Two approaches exist for calling ffmpeg from Python:

**Approach A: `ffmpeg-python` wrapper**

```python
import ffmpeg

# Fluent API
(
    ffmpeg
    .input('video.mp4')
    .output('audio.wav', vn=None, ar=16000, ac=1)
    .run(quiet=True)
)
```

| Pros | Cons |
|---|---|
| Pythonic, composable API | Thin wrapper — still spawns subprocess under the hood |
| Type hints, IDE-friendly | Adds dependency for minimal value |
| Filter graph construction | Slightly slower than raw subprocess (negligible) |

**Approach B: Direct subprocess**

```python
import subprocess

cmd = [
    'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
    '-i', 'video.mp4',
    '-vn', '-ar', '16000', '-ac', '1',
    'audio.wav'
]
subprocess.run(cmd, check=True)
```

| Pros | Cons |
|---|---|
| Zero dependencies beyond ffmpeg binary | Verbose for complex filter graphs |
| Full access to all ffmpeg features | Requires familiarity with CLI syntax |
| Fastest execution path | Error handling is manual |

**Mnemosyne Recommendation:** Use **direct subprocess** for the satellite. The `ffmpeg-python` wrapper adds a dependency for minimal abstraction value. The satellite's job is to run ffmpeg commands reliably, not to compose complex filter graphs programmatically.

---

## 5. The Complete Pipeline

### 5.1 End-to-End Flow

```
URL / Local File
    |
    v
[yt-dlp]  -- Extract metadata + audio stream (if URL)
    |
    v
[ffmpeg]  -- Normalize to 16kHz mono WAV, segment if >2hr
    |
    v
[whisperx] -- Transcribe + align + diarize
    |
    v
[JSON]    -- RawDocument with segments, speakers, timestamps
    |
    v
[Rust Core] -- Ingest into state.db
```

### 5.2 Pipeline Code Example

```python
import os
import json
import subprocess
import tempfile
import whisperx
import yt_dlp

def process_video_source(source: str, output_json: str, hf_token: str = None):
    # source can be a URL or local file path
    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: Extract metadata and audio
        if source.startswith(('http://', 'https://')):
            metadata = extract_metadata(source)
            audio_path = os.path.join(tmpdir, 'audio.wav')
            extract_audio(source, audio_path)
        else:
            metadata = {
                'source_file': source,
                'source_type': 'local_audio_video',
            }
            audio_path = os.path.join(tmpdir, 'audio.wav')
            normalize_audio(source, audio_path)

        # Step 2: Segment if >2 hours or >2GB
        segments = segment_audio(audio_path, tmpdir)

        # Step 3: Transcribe with whisperx
        all_segments = []
        for seg_path in segments:
            result = transcribe_segment(seg_path, hf_token)
            all_segments.extend(result['segments'])

        # Step 4: Build RawDocument
        doc = build_raw_document(metadata, all_segments)
        with open(output_json, 'w') as f:
            json.dump(doc, f, indent=2)

def extract_metadata(url: str) -> dict:
    opts = {'quiet': True, 'skip_download': True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {k: info.get(k) for k in [
        'id', 'title', 'description', 'uploader', 'channel',
        'upload_date', 'duration', 'view_count', 'like_count',
        'tags', 'categories', 'chapters', 'webpage_url', 'extractor'
    ]}

def extract_audio(url: str, output_path: str):
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path.replace('.wav', ''),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '0',
        }],
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

def normalize_audio(input_path: str, output_path: str):
    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-i', input_path,
        '-vn', '-ar', '16000', '-ac', '1',
        '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
        output_path
    ]
    subprocess.run(cmd, check=True)

def segment_audio(audio_path: str, tmpdir: str, max_duration: int = 7200) -> list:
    # Get duration
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
        capture_output=True, text=True, check=True
    )
    duration = float(probe.stdout.strip())
    if duration <= max_duration:
        return [audio_path]
    
    # Segment at 30-minute chunks
    pattern = os.path.join(tmpdir, 'segment_%03d.wav')
    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-i', audio_path,
        '-f', 'segment', '-segment_time', '1800',
        '-c', 'copy', pattern
    ]
    subprocess.run(cmd, check=True)
    return sorted([
        os.path.join(tmpdir, f) for f in os.listdir(tmpdir)
        if f.startswith('segment_')
    ])

def transcribe_segment(audio_path: str, hf_token: str = None) -> dict:
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    batch_size = 16 if device == 'cuda' else 4
    compute_type = 'float16' if device == 'cuda' else 'int8'
    
    # Load audio
    audio = whisperx.load_audio(audio_path)
    
    # 1. Transcribe
    model = whisperx.load_model('large-v3', device, compute_type=compute_type)
    result = model.transcribe(audio, batch_size=batch_size)
    
    # 2. Align (word-level timestamps)
    align_model, metadata = whisperx.load_align_model(
        language_code=result['language'], device=device
    )
    result = whisperx.align(result['segments'], align_model, metadata, audio, device)
    
    # 3. Diarize (if token provided)
    if hf_token:
        diarize_model = whisperx.DiarizationPipeline(use_auth_token=hf_token, device=device)
        diarize_segments = diarize_model(audio, min_speakers=2, max_speakers=6)
        result = whisperx.assign_word_speakers(diarize_segments, result)
    
    return result

def build_raw_document(metadata: dict, segments: list) -> dict:
    return {
        'source_file': metadata.get('webpage_url') or metadata.get('source_file'),
        'source_type': 'video' if metadata.get('webpage_url') else 'audio',
        'extractor': 'whisperx',
        'extractor_version': '3.0',
        'metadata': {
            'title': metadata.get('title'),
            'author': metadata.get('uploader') or metadata.get('channel'),
            'duration_seconds': metadata.get('duration'),
            'upload_date': metadata.get('upload_date'),
            'platform': metadata.get('extractor'),
            'view_count': metadata.get('view_count'),
            'tags': metadata.get('tags', []),
            'categories': metadata.get('categories', []),
        },
        'segments': [
            {
                'start': seg.get('start'),
                'end': seg.get('end'),
                'text': seg.get('text', '').strip(),
                'speaker': seg.get('speaker', 'UNKNOWN'),
                'words': [
                    {
                        'word': w.get('word'),
                        'start': w.get('start'),
                        'end': w.get('end'),
                        'speaker': w.get('speaker', 'UNKNOWN')
                    }
                    for w in seg.get('words', [])
                ],
                'confidence': seg.get('confidence')  # if available
            }
            for seg in segments
        ],
        'provenance': {
            'model': 'large-v3',
            'alignment': True,
            'diarization': hf_token is not None,
            'language': result.get('language'),
            'segment_count': len(segments),
        }
    }
```

---

## 6. Output JSON Schema (`RawDocument`)

```json
{
  "source_file": "https://youtube.com/watch?v=abc123",
  "source_type": "video",
  "extractor": "whisperx",
  "extractor_version": "3.0",
  "metadata": {
    "title": "The Future of AI Agents",
    "author": "Lex Fridman",
    "duration_seconds": 7200,
    "upload_date": "20260115",
    "platform": "youtube",
    "view_count": 2500000,
    "tags": ["AI", "agents", "interview"],
    "categories": ["Science & Technology"]
  },
  "segments": [
    {
      "start": 0.0,
      "end": 5.32,
      "text": "The following is a conversation with Demis Hassabis.",
      "speaker": "SPEAKER_00",
      "words": [
        {"word": "The", "start": 0.0, "end": 0.12, "speaker": "SPEAKER_00"},
        {"word": "following", "start": 0.15, "end": 0.45, "speaker": "SPEAKER_00"},
        {"word": "is", "start": 0.48, "end": 0.58, "speaker": "SPEAKER_00"}
      ]
    },
    {
      "start": 5.32,
      "end": 12.10,
      "text": "Thank you for having me on, Lex.",
      "speaker": "SPEAKER_01",
      "words": [...]
    }
  ],
  "provenance": {
    "model": "large-v3",
    "alignment": true,
    "diarization": true,
    "language": "en",
    "segment_count": 1428,
    "processing_time_seconds": 240,
    "yt_dlp_version": "2026.01.01"
  }
}
```

---

## 7. Provenance Mapping to `state.db`

The `pages` table's `provenance` JSON field stores:

```json
[
  {
    "source_file": "https://youtube.com/watch?v=abc123",
    "extractor": "whisperx",
    "extractor_version": "3.0",
    "model": "large-v3",
    "language": "en",
    "alignment": true,
    "diarization": true,
    "segment_count": 1428,
    "speaker_count": 2,
    "duration_seconds": 7200,
    "processing_time_seconds": 240,
    "yt_dlp_version": "2026.01.01",
    "ffmpeg_normalization": "16kHz_mono_loudnorm"
  }
]
```

The `links` table can store speaker relationships:
```json
{
  "source_page_id": "page-uuid",
  "target_page_id": "speaker-uuid",
  "link_type": "semantic",
  "context": "SPEAKER_01 identified as Demis Hassabis via manual mapping"
}
```

---

## 8. Licensing & Compliance

| Component | License | Mnemosyne Impact |
|---|---|---|
| `openai-whisper` | MIT | Zero friction |
| `faster-whisper` | MIT | Zero friction |
| `whisperx` | Apache-2.0 | Zero friction |
| `yt-dlp` | Unlicense | Zero friction (public domain) |
| `ffmpeg` | LGPL-2.1+/GPL-2.0+ | Subprocess use = no linking; compliant |
| `pyannote.audio` | MIT | Zero friction |
| `torch` / `transformers` | BSD-3-Clause | Zero friction |

**All transcription stack components are permissively licensed.** No AGPL concerns.

---

## 9. Hardware & Performance Targets

### 9.1 Foundry Node (Batch Processing)

| Hardware | Transcription | + Alignment | + Diarization |
|---|---|---|---|
| RTX 4090 (FP16) | 72x RTF | 60x | 30x |
| RTX 4070 (FP16) | 50x | 40x | 22x |
| RTX 3060 (INT8) | 35x | 28x | 12x |
| Apple M4 Max (MPS) | 25x | 20x | 8x |
| Ryzen 7 7700X (CPU) | 10x | 8x | 0.5x (impractical) |

**RTF = Real-Time Factor.** 72x RTF means 1 hour of audio processes in 50 seconds.

**VRAM requirements:** 6 GB minimum, 8 GB+ comfortable for Large-v3. Turbo model fits in 4 GB.

### 9.2 Strix Halo Target (Ryzen AI Max+ 395)

The Strix Halo APU (128 GB unified LPDDR5X) is Mnemosyne's target hardware. With ROCm support:
- Large-v3 Turbo should run at ~20-30x RTF on the integrated RDNA 3.5 GPU.
- Full Large-v3 may require vLLM/SGLang fallback or CPU offload for diarization.
- CPU fallback (INT8) is viable for overnight batch processing.

---

## 10. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| yt-dlp extractor breaks (YouTube changes) | High | Medium | Auto-update yt-dlp weekly; fallback to local file ingestion |
| PO token blocking on YouTube | Medium | Medium | Use cookies; rotate proxies; accept some failures |
| Whisper hallucination on poor audio | Medium | Medium | VAD preprocessing; Demucs separation; human review flag |
| Diarization accuracy poor (>4 speakers) | Medium | Low | Set min/max speakers; warn in provenance; allow manual correction |
| GPU OOM with Large-v3 | Low | High | Use Turbo model; reduce batch_size; CPU fallback |
| Long files (>2hr) cause instability | Medium | Medium | Pre-segment at silence boundaries |
| HuggingFace token required for pyannote | Low | Low | Document setup; cache models locally |
| ffmpeg not installed on target system | Low | High | Bundle ffmpeg binary with satellite; or require system dependency |
| Language misidentification | Low | Medium | Allow `--language` override in config; default to explicit setting |

---

## 11. Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-27 | Python satellite for all audio/video transcription | Rust has no equivalent ASR ecosystem |
| 2026-05-27 | `whisperx` as default transcription engine | Word-level alignment + diarization + Apache-2.0 license |
| 2026-05-27 | `faster-whisper` as fallback for simple content | Speed when diarization unnecessary |
| 2026-05-27 | `yt-dlp` for URL-based audio extraction | 1,700+ platforms; rich metadata; Unlicense |
| 2026-05-27 | Direct ffmpeg subprocess (not `ffmpeg-python`) | Zero extra dependency; full CLI access |
| 2026-05-27 | Pre-segment audio at 30min / 2GB boundaries | Whisper stability on long files |
| 2026-05-27 | Loudnorm + 16kHz mono normalization | Consistent input for Whisper; better accuracy |
| 2026-05-27 | Large-v3 Turbo as default model | Speed/accuracy sweet spot for local GPU |

---

## 12. Open Questions

1. **Should we extract existing captions/subtitles instead of transcribing?** YouTube auto-captions exist for many videos. yt-dlp can download them. This is faster and cheaper but may be lower quality than Whisper. Offer as opt-in?
2. **Speaker name mapping:** WhisperX labels `SPEAKER_00`, `SPEAKER_01`. Should Mnemosyne offer a UI to map these to real names, storing the mapping in the `links` table?
3. **Video frame extraction for visual context:** Should we extract keyframes (e.g., every 30 seconds) and run them through a vision model to generate image descriptions that enrich the transcript?
4. **Live stream ingestion:** yt-dlp supports livestream downloading. Should Mnemosyne support real-time or near-real-time transcription of live content?
5. **Music separation before transcription:** For content with background music, should we run Demucs/Spleeter separation before Whisper to improve accuracy? Adds ~2x processing time.
6. **Chapter-aware segmentation:** YouTube chapters provide semantic boundaries. Should we use them instead of time-based segmentation when available?

---

## 13. References

- [OpenAI Whisper GitHub](https://github.com/openai/whisper) — Official implementation
- [Faster-Whisper GitHub](https://github.com/SYSTRAN/faster-whisper) — CTranslate2 production port
- [WhisperX GitHub](https://github.com/m-bain/whisperX) — Alignment + diarization layer
- [WhisperX 2026 Guide](https://localaimaster.com/blog/whisperx-guide) — Comprehensive setup and tuning
- [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp) — Video/audio extraction
- [yt-dlp Cheat Sheet](https://www.ditig.com/yt-dlp-cheat-sheet) — Command reference
- [FFmpeg Documentation](https://ffmpeg.org/documentation.html) — Official docs
- [How to Use FFmpeg with Python 2026](https://www.gumlet.com/learn/ffmpeg-python/) — Integration guide
- [Whisper Accuracy 2026](https://novascribe.ai/how-accurate-is-whisper) — WER benchmarks and model comparison
- [Whisper Speaker Diarization Guide 2026](https://brasstranscripts.com/blog/whisper-speaker-diarization-guide) — Pyannote integration tutorial