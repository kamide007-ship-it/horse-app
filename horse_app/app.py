from __future__ import annotations

import os
import json
import uuid
from typing import Optional, Dict, Any

from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
from werkzeug.utils import secure_filename

from .services.netkeiba_fetcher import fetch_netkeiba_metrics
from .services.jbis_normalizer import fetch_jbis_csv_bytes, normalize_jbis_csv
from .services.keibago_fetcher import update_track_level_from_csv_url, load_track_level
from .services.nankankeiba_loader import update_nankan_map_from_csv_url, load_nankan_map
from .services.broodmare_market_loader import update_market_from_csv_url, update_market_from_upload, load_market
from .services.evaluator import build_report_summary

APP_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
DATA_DIR = os.path.join(APP_DIR, "data")
CONFIG_JSON = os.path.join(DATA_DIR, "config.json")

ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp"}
ALLOWED_CSV_EXT = {"csv"}

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")

def allowed_file(filename: str, allowed: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed

def load_config() -> dict:
    try:
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def save_config(d: dict) -> None:
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def require_admin_token() -> bool:
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        return True  # token未設定なら誰でも更新可（個人利用想定）
    provided = request.args.get("token", "")
    return provided == token

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/evaluate")
def evaluate():
    horse_name = (request.form.get("horse_name") or "").strip()
    if not horse_name:
        flash("馬名を入力してください。")
        return redirect(url_for("index"))

    include_broodmare = request.form.get("include_broodmare") == "1"
    sire_line = (request.form.get("sire_line") or "").strip() or None
    dam_sire_line = (request.form.get("dam_sire_line") or "").strip() or None

    # 南関補正の入力（任意）
    nankan_style = (request.form.get("nankan_style") or "").strip() or None
    nankan_distance = (request.form.get("nankan_distance") or "").strip() or None

    # データURL（任意）
    keibago_csv_url = (request.form.get("keibago_csv_url") or "").strip() or None
    nankan_csv_url = (request.form.get("nankan_csv_url") or "").strip() or None
    broodmare_trade_csv_url = (request.form.get("broodmare_trade_csv_url") or "").strip() or None

    # 設定保存（次回 refresh-data で使う）
    cfg = load_config()
    if keibago_csv_url: cfg["keibago_csv_url"] = keibago_csv_url
    if nankan_csv_url: cfg["nankan_csv_url"] = nankan_csv_url
    if broodmare_trade_csv_url: cfg["broodmare_trade_csv_url"] = broodmare_trade_csv_url
    save_config(cfg)

    # 画像アップロード（任意）
    image_path: Optional[str] = None
    img = request.files.get("horse_image")
    if img and img.filename:
        if not allowed_file(img.filename, ALLOWED_IMAGE_EXT):
            flash("画像は jpg / jpeg / png / webp のみ対応です。")
            return redirect(url_for("index"))
        ext = img.filename.rsplit(".", 1)[1].lower()
        save_name = f"{uuid.uuid4().hex}.{ext}"
        image_path = os.path.join(UPLOAD_DIR, secure_filename(save_name))
        img.save(image_path)

    # netkeiba（URLのみ、任意）
    netkeiba_url = (request.form.get("netkeiba_result_url") or "").strip()
    netkeiba_metrics = None
    if netkeiba_url:
        try:
            netkeiba_metrics = fetch_netkeiba_metrics(netkeiba_url)
        except Exception:
            netkeiba_metrics = None

    # JBIS（URL or Upload）
    jbis_metrics = None
    jbis_csv_url = (request.form.get("jbis_csv_url") or "").strip()
    jbis_file = request.files.get("jbis_csv_file")
    try:
        raw = None
        if jbis_csv_url:
            raw = fetch_jbis_csv_bytes(jbis_csv_url)
        elif jbis_file and jbis_file.filename and allowed_file(jbis_file.filename, ALLOWED_CSV_EXT):
            raw = jbis_file.read()
        if raw:
            jbis_metrics = normalize_jbis_csv(raw)
    except Exception:
        jbis_metrics = None

    # STEP1/2/3: 入力URLがあればその場で更新（無ければ既存JSON or フォールバック）
    if keibago_csv_url:
        try:
            update_track_level_from_csv_url(keibago_csv_url)
        except Exception:
            pass

    if nankan_csv_url:
        try:
            update_nankan_map_from_csv_url(nankan_csv_url)
        except Exception:
            pass

    if broodmare_trade_csv_url:
        try:
            update_market_from_csv_url(broodmare_trade_csv_url)
        except Exception:
            pass

    report = build_report_summary(
        horse_name=horse_name,
        include_broodmare=include_broodmare,
        sire_line=sire_line,
        dam_sire_line=dam_sire_line,
        netkeiba_metrics=netkeiba_metrics,
        jbis_metrics=jbis_metrics,
        has_image=bool(image_path),
        image_path=image_path,
        nankan_style=nankan_style,
        nankan_distance=nankan_distance,
    )

    return render_template("result.html", horse_name=horse_name, report=report)

@app.get("/admin/refresh-data")
def refresh_data():
    if not require_admin_token():
        return "Forbidden (bad token)", 403

    cfg = load_config()
    out: Dict[str, Any] = {"updated": {}, "errors": {}}

    keibago_url = cfg.get("keibago_csv_url")
    if keibago_url:
        try:
            out["updated"]["track_level"] = update_track_level_from_csv_url(keibago_url)
        except Exception as e:
            out["errors"]["track_level"] = str(e)

    nankan_url = cfg.get("nankan_csv_url")
    if nankan_url:
        try:
            out["updated"]["nankan_map"] = update_nankan_map_from_csv_url(nankan_url)
        except Exception as e:
            out["errors"]["nankan_map"] = str(e)

    trade_url = cfg.get("broodmare_trade_csv_url")
    if trade_url:
        try:
            out["updated"]["broodmare_market"] = update_market_from_csv_url(trade_url)
        except Exception as e:
            out["errors"]["broodmare_market"] = str(e)

    return jsonify(out)

@app.get("/status")
def status():
    cfg = load_config()
    return jsonify({
        "config": cfg,
        "track_level": load_track_level(),
        "nankan_map_size": len(load_nankan_map()),
        "broodmare_market": load_market(),
        "admin_token_enabled": bool(os.environ.get("ADMIN_TOKEN")),
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
