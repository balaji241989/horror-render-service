# make_longform.py
import os, re, glob
from typing import Tuple, List, Optional
from moviepy.editor import (
    ImageClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
)
from moviepy.audio.fx.all import audio_loop

# Pillow ≥10 safety (ANTIALIAS moved)
try:
    from PIL import Image  # noqa
    if not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = Image.Resampling.LANCZOS  # type: ignore
except Exception:
    pass

def _numeric_key(name: str):
    m = re.search(r'\d+', name)
    return int(m.group()) if m else name.lower()

def _list_images(images_dir: str, order: str) -> List[str]:
    paths: List[str] = []
    for pat in ("*.jpg","*.jpeg","*.png","*.webp"):
        paths.extend(glob.glob(os.path.join(images_dir, pat)))
    if not paths:
        raise RuntimeError("No images found in images_dir")
    # numeric, then name
    paths.sort(key=lambda p: (_numeric_key(os.path.basename(p)), os.path.basename(p).lower()))
    if order == "name_desc":
        paths.reverse()
    return paths

def render_longform(
    images_dir: str,
    voiceover_path: str,
    ambient_path: Optional[str],
    output_path: str,
    size: Tuple[int,int]=(1080,1920),
    fps: int=30,
    crossfade: float=0.5,
    ambient_gain: float=0.25,
    master_gain: float=1.0,
    pad_tail: float=0.25,
    order: str="name_asc",
) -> None:
    """Render a vertical longform video by fitting image durations to VO length, with optional ambient bed."""
    imgs = _list_images(images_dir, order)
    vo = AudioFileClip(voiceover_path)
    vo_duration = vo.duration

    n = len(imgs)
    # time per image so that total ≈ VO + pad_tail with crossfades accounted
    per = max(0.2, (vo_duration - max(0, n-1)*max(0.0, crossfade)) / n)

    clips = []
    for idx, path in enumerate(imgs):
        c = ImageClip(path).resize(size).set_duration(per)
        if idx > 0 and crossfade > 0:
            c = c.crossfadein(crossfade)
        clips.append(c)

    if crossfade > 0 and len(clips) > 1:
        video = concatenate_videoclips(clips, method="compose", padding=-crossfade)
    else:
        video = concatenate_videoclips(clips, method="compose")

    total_dur = max(vo_duration + pad_tail, video.duration)

    # audio: VO + ambient loop (optional)
    if ambient_path:
        amb = AudioFileClip(ambient_path)
        amb_loop = audio_loop(amb, duration=total_dur).volumex(ambient_gain)
        audio = CompositeAudioClip([amb_loop.set_start(0), vo.set_start(0)])
    else:
        audio = vo

    if master_gain != 1.0:
        audio = audio.volumex(master_gain)

    out = video.set_audio(audio).set_fps(fps).set_duration(total_dur)
    out.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=fps,
        threads=4,
        preset="medium",
        bitrate="6000k"
    )
