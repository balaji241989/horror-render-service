import os, tempfile, zipfile, uuid, shutil
from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
from make_longform import render_longform

API_KEY = os.getenv("API_KEY", "changeme")
app = Flask(__name__)

@app.get("/health")
def health():
    return {"ok": True, "service": "longform-render", "version": "1.0.0"}

def _authed(req):
    k = req.headers.get("x-api-key") or req.form.get("api_key")
    return bool(k) and k == API_KEY

@app.post("/render")
def render_endpoint():
    if not _authed(request):
        return jsonify(error="Unauthorized"), 401
    tmpdir = tempfile.mkdtemp(prefix="lf_")
    outpath = os.path.join(tmpdir, f"out_{uuid.uuid4().hex}.mp4")
    try:
        # images (zip or multiple files)
        images_dir = os.path.join(tmpdir, "images"); os.makedirs(images_dir, exist_ok=True)
        if "images_zip" in request.files:
            with zipfile.ZipFile(request.files["images_zip"]) as zf:
                zf.extractall(images_dir)
        else:
            files = request.files.getlist("images")
            if not files: return jsonify(error="No images provided"), 400
            for f in files:
                fn = secure_filename(f.filename or f"img_{uuid.uuid4().hex}.jpg")
                f.save(os.path.join(images_dir, fn))

        # voiceover (required)
        if "voiceover" not in request.files:
            return jsonify(error="voiceover file missing"), 400
        vo_path = os.path.join(tmpdir, "voiceover.mp3")
        request.files["voiceover"].save(vo_path)

        # ambient (optional)
        amb_path = None
        if "ambient" in request.files:
            amb_path = os.path.join(tmpdir, "ambient.mp3")
            request.files["ambient"].save(amb_path)

        # params
        fps         = int(request.form.get("fps", 30))
        width       = int(request.form.get("width", 1080))
        height      = int(request.form.get("height", 1920))
        crossfade   = float(request.form.get("crossfade", 0.5))
        ambient_gain= float(request.form.get("ambient_gain", 0.25))
        master_gain = float(request.form.get("master_gain", 1.0))
        pad_tail    = float(request.form.get("pad_tail", 0.25))
        order       = request.form.get("order", "name_asc")

        render_longform(
            images_dir=images_dir,
            voiceover_path=vo_path,
            ambient_path=amb_path,
            output_path=outpath,
            size=(width, height),
            fps=fps,
            crossfade=crossfade,
            ambient_gain=ambient_gain,
            master_gain=master_gain,
            pad_tail=pad_tail,
            order=order
        )
        return send_file(outpath, mimetype="video/mp4", as_attachment=True, download_name="longform.mp4")
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        try: shutil.rmtree(tmpdir)
        except Exception: pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
