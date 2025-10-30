# app.py
import os, tempfile, zipfile, uuid, shutil, requests
from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
from make_longform import render_longform

API_KEY = os.getenv("API_KEY", "changeme")
app = Flask(__name__)

@app.get("/health")
def health():
    return {"ok": True, "service": "longform-render", "version": "1.1.0"}

def _authed(req):
    k = req.headers.get("x-api-key") or req.form.get("api_key")
    return bool(k) and k == API_KEY

def _download(url: str, dest_path: str, chunk=1 << 15):
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        for b in r.iter_content(chunk_size=chunk):
            if b:
                f.write(b)

@app.post("/render")  # existing upload mode (unchanged)
def render_endpoint():
    if not _authed(request):
        return jsonify(error="Unauthorized"), 401
    tmpdir = tempfile.mkdtemp(prefix="lf_"); outpath = os.path.join(tmpdir, f"out_{uuid.uuid4().hex}.mp4")
    try:
        images_dir = os.path.join(tmpdir, "images"); os.makedirs(images_dir, exist_ok=True)
        if "images_zip" in request.files:
            with zipfile.ZipFile(request.files["images_zip"]) as zf: zf.extractall(images_dir)
        else:
            files = request.files.getlist("images")
            if not files: return jsonify(error="No images provided"), 400
            for f in files:
                fn = secure_filename(f.filename or f"img_{uuid.uuid4().hex}.jpg")
                f.save(os.path.join(images_dir, fn))

        if "voiceover" not in request.files: return jsonify(error="voiceover file missing"), 400
        vo_path = os.path.join(tmpdir, "voiceover.mp3"); request.files["voiceover"].save(vo_path)

        amb_path = None
        if "ambient" in request.files:
            amb_path = os.path.join(tmpdir, "ambient.mp3"); request.files["ambient"].save(amb_path)

        fps=int(request.form.get("fps",30)); width=int(request.form.get("width",1080)); height=int(request.form.get("height",1920))
        crossfade=float(request.form.get("crossfade",0.5)); ambient_gain=float(request.form.get("ambient_gain",0.25))
        master_gain=float(request.form.get("master_gain",1.0)); pad_tail=float(request.form.get("pad_tail",0.25))
        order=request.form.get("order","name_asc")

        render_longform(images_dir, vo_path, amb_path, outpath, (width,height), fps, crossfade, ambient_gain, master_gain, pad_tail, order)
        return send_file(outpath, mimetype="video/mp4", as_attachment=True, download_name="longform.mp4")
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        try: shutil.rmtree(tmpdir)
        except: pass

@app.post("/render_urls")  # NEW: Drive-pull mode (JSON body)
def render_from_urls():
    if not _authed(request):
        return jsonify(error="Unauthorized"), 401
    data = request.get_json(silent=True) or {}
    images = data.get("images") or []
    vo_url = data.get("voiceover_url")
    amb_url = data.get("ambient_url")

    if not images or not vo_url:
        return jsonify(error="images[] and voiceover_url are required"), 400

    tmpdir = tempfile.mkdtemp(prefix="lf_"); outpath = os.path.join(tmpdir, f"out_{uuid.uuid4().hex}.mp4")
    try:
        images_dir = os.path.join(tmpdir, "images"); os.makedirs(images_dir, exist_ok=True)
        # download images
        for idx, url in enumerate(images, start=1):
            ext = ".jpg"
            if ".png" in url.lower(): ext = ".png"
            _download(url, os.path.join(images_dir, f"{idx:04d}{ext}"))

        # download audio
        vo_path = os.path.join(tmpdir, "voiceover.mp3"); _download(vo_url, vo_path)
        amb_path = None
        if amb_url:
            amb_path = os.path.join(tmpdir, "ambient.mp3"); _download(amb_url, amb_path)

        # params
        fps=int(data.get("fps",30)); w=int(data.get("width",1080)); h=int(data.get("height",1920))
        crossfade=float(data.get("crossfade",0.5)); ambient_gain=float(data.get("ambient_gain",0.25))
        master_gain=float(data.get("master_gain",1.0)); pad_tail=float(data.get("pad_tail",0.25))
        order=data.get("order","name_asc")

        render_longform(images_dir, vo_path, amb_path, outpath, (w,h), fps, crossfade, ambient_gain, master_gain, pad_tail, order)
        return send_file(outpath, mimetype="video/mp4", as_attachment=True, download_name="longform.mp4")
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        try: shutil.rmtree(tmpdir)
        except: pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
