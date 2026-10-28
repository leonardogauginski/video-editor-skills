#!/usr/bin/env python3
"""Monta o cozy_youtube_final.mp4 a partir do edl.json.

Uso:
  python3 render.py --src "pasta/com/os/WhatsApp Video..." [--out cozy_youtube_final.mp4] [--work pasta_temp]

Precisa de ffmpeg (com libvidstab) e Python 3.9+ com numpy.
Para ajustar o video, edite o edl.json (tempos, ordem, cenas) ou as constantes
abaixo (cor, volume, transicoes) e rode de novo. Os originais nunca sao alterados.
"""
import argparse, glob, json, math, os, re, subprocess, sys
import numpy as np

W, H, FPS = 1920, 1080, 30
XFADE = 0.8            # dissolve entre cenas (s)
EDGE_FADE = 0.06       # micro fade de audio em cada corte seco (evita estalos)
TARGET_LUMA = 0.46     # exposicao alvo (media 0-1)
EXPO_STRENGTH = 0.5    # 0 = sem correcao de exposicao, 1 = total
WB_STRENGTH = 0.45     # 0 = sem balanco de branco automatico, 1 = gray world total
TARGET_DB = -27.0      # nivel medio de cada trecho antes do loudnorm final
MAX_GAIN_DB = 9.0
# visual "cozy" comum a todos os trechos: um pouco mais quente, contraste suave
COZY_GRADE = ("colortemperature=temperature=5600:mix=0.55:pl=0.4,"
              "eq=contrast=1.03:saturation=1.04,"
              "curves=all='0/0.025 0.25/0.24 0.5/0.5 0.75/0.77 1/0.975'")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"falhou: {' '.join(cmd)}\n{r.stderr[-3000:]}")
    return r


def find_src(src_dir, key):
    hits = [p for p in glob.glob(os.path.join(src_dir, "*.mp4")) if key in os.path.basename(p)]
    if not hits:
        sys.exit(f"nao achei o arquivo {key} em {src_dir}")
    return hits[0]


def in_args(c, path):
    pre = ["-noautorotate"] if c.get("orient") == "raw" else []
    return pre + ["-ss", f"{c['in']:.3f}", "-t", f"{c['out'] - c['in']:.3f}", "-i", path]


def analyse(c, path):
    """Media de cor/luz do trecho (2 quadros/s) para harmonizar os clipes."""
    r = subprocess.run(["ffmpeg", "-v", "error", *in_args(c, path), "-vf", "fps=2,scale=96:-2",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, np.uint8).reshape(-1, 3).astype(np.float32) / 255
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    mid = a[(lum > 0.12) & (lum < 0.88)]          # ignora ceu estourado e sombras
    m = mid.mean(0) if len(mid) else a.mean(0)
    gray = m.mean()
    gains = np.clip((gray / m) ** WB_STRENGTH, 0.92, 1.08)
    gains = gains / gains.mean()
    gamma = math.log(TARGET_LUMA) / math.log(max(0.05, min(0.95, float(lum.mean()))))
    gamma = float(np.clip(1 + (gamma - 1) * EXPO_STRENGTH, 0.82, 1.22))
    vol = subprocess.run(["ffmpeg", "-v", "info", *in_args(c, path), "-vn", "-af", "volumedetect",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    mv = re.search(r"mean_volume: (-?[\d.]+)", vol)
    mean_db = float(mv.group(1)) if mv else TARGET_DB
    gain_db = float(np.clip(TARGET_DB - mean_db, -MAX_GAIN_DB, MAX_GAIN_DB)) + c.get("gain_db", 0)
    return gains, gamma, gain_db


def render_clip(c, path, out, work, first, last):
    dur = c["out"] - c["in"]
    gains, gamma, gain_db = analyse(c, path)
    # eq gamma >1 clareia; queremos clarear quando a media esta abaixo do alvo
    color = (f"colorchannelmixer=rr={gains[0]:.4f}:gg={gains[1]:.4f}:bb={gains[2]:.4f},"
             f"eq=gamma={1/gamma:.4f},{COZY_GRADE}")
    pre = f"fps={FPS},setpts=PTS-STARTPTS"
    if c.get("stab"):
        trf = os.path.join(work, os.path.basename(out) + ".trf")
        run(["ffmpeg", "-y", "-v", "error", *in_args(c, path), "-vf",
             f"{pre},vidstabdetect=shakiness=6:accuracy=12:result={trf}", "-f", "null", "-"])
        pre += f",vidstabtransform=input={trf}:smoothing=20:zoom=4:optzoom=0,unsharp=5:5:0.5"
    if c.get("orient") == "vertical":
        # vertical: imagem inteira centralizada + copia ampliada e desfocada ao fundo
        vf = (f"[0:v]{pre},{color},split[a][b];"
              f"[a]scale={W}:{H}:force_original_aspect_ratio=increase:flags=bicubic,crop={W}:{H},"
              f"gblur=sigma=70,eq=brightness=-0.10:saturation=0.75[bg];"
              f"[b]scale=-2:{H}:flags=lanczos,unsharp=5:5:0.45[fg];"
              f"[bg][fg]overlay=(W-w)/2:0,setsar=1,format=yuv420p[v]")
    else:
        if c.get("crop"):  # pequeno ajuste de enquadramento, mesma proporcao
            x, y, w = c["crop"]
            pre += f",crop=iw*{w}:ih*{w}:iw*{x}:ih*{y}"
        vf = (f"[0:v]{pre},{color},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
              f"crop={W}:{H},unsharp=5:5:0.45,setsar=1,format=yuv420p[v]")
    fi = 0.35 if first else EDGE_FADE
    fo = 0.35 if last else EDGE_FADE
    af = (f"[0:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS,"
          f"highpass=f=70,afftdn=nf=-28,volume={gain_db:.2f}dB,"
          f"afade=t=in:d={fi},afade=t=out:st={max(0, dur - fo):.3f}:d={fo},apad,atrim=0:{dur:.3f}[a]")
    run(["ffmpeg", "-y", "-v", "error", *in_args(c, path), "-filter_complex", f"{vf};{af}",
         "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "12", "-g", "30",
         "-c:a", "pcm_s16le", out])
    return dur


def probe_dur(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", p]).stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--edl", default=os.path.join(os.path.dirname(__file__), "edl.json"))
    ap.add_argument("--out", default="cozy_youtube_final.mp4")
    ap.add_argument("--work", default="cozy_work")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    edl = json.load(open(a.edl))
    scene_files = []
    for si, s in enumerate(edl["scenes"]):
        parts = []
        for ci, c in enumerate(s["clips"]):
            out = os.path.join(a.work, f"s{si:02d}_c{ci:02d}.mkv")
            print(f"[{si+1}/{len(edl['scenes'])}] {s['name']}: {c['file']} {c['in']}-{c['out']}", flush=True)
            render_clip(c, find_src(a.src, c["file"]), out, a.work, ci == 0, ci == len(s["clips"]) - 1)
            parts.append(out)
        lst = os.path.join(a.work, f"s{si:02d}.txt")
        open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
        sf = os.path.join(a.work, f"scene{si:02d}.mkv")
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", sf])
        scene_files.append(sf)

    # dissolves entre cenas + fade do preto no inicio e para o preto no final
    durs = [probe_dur(f) for f in scene_files]
    inputs, fc = [], []
    for f in scene_files:
        inputs += ["-i", f]
    v, au, t = "[0:v]", "[0:a]", durs[0]
    for i in range(1, len(scene_files)):
        off = t - XFADE
        fc.append(f"{v}[{i}:v]xfade=transition=fade:duration={XFADE}:offset={off:.3f}[v{i}]")
        fc.append(f"{au}[{i}:a]acrossfade=d={XFADE}:c1=tri:c2=tri[a{i}]")
        v, au, t = f"[v{i}]", f"[a{i}]", off + durs[i]
    fc.append(f"{v}fade=t=in:d=1.2,fade=t=out:st={t - 2.2:.3f}:d=2.2,format=yuv420p[vf]")
    fc.append(f"{au}afade=t=in:d=1.0,afade=t=out:st={t - 2.5:.3f}:d=2.5,"
              f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[af]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc),
         "-map", "[vf]", "-map", "[af]", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-maxrate", "16M", "-bufsize", "32M", "-profile:v", "high", "-pix_fmt", "yuv420p",
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", a.out])
    print(f"pronto: {a.out} ({t:.1f}s)")


if __name__ == "__main__":
    main()
