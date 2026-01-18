from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import stripe
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db, login_manager
from models import Evaluation, User
from services.evaluator import evaluate_horse
from services.body_predictor import make_3yo_prediction_image
from services.market import estimate_market
from stripe_service import create_checkout_session, handle_webhook

APP_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = APP_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///app.db")
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgres://"):
        app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        db.create_all()

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "ts": datetime.utcnow().isoformat()}

    # ---- Auth ----
    @app.route("/register", methods=["GET", "POST"])
    def auth_register():
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            if not email or not password:
                flash("メールとパスワードを入力してください。")
                return render_template("register.html")
            if User.query.filter_by(email=email).first():
                flash("そのメールは既に登録されています。")
                return render_template("register.html")
            u = User(email=email)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            return redirect(url_for("pricing"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def auth_login():
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            u = User.query.filter_by(email=email).first()
            if u and u.check_password(password):
                login_user(u)
                return redirect(url_for("index"))
            flash("ログインに失敗しました。")
        return render_template("login.html")

    @app.get("/logout")
    def auth_logout():
        logout_user()
        return redirect(url_for("auth_login"))

    # ---- Pricing ----
    @app.get("/pricing")
    @login_required
    def pricing():
        return render_template("pricing.html")

    @app.post("/checkout/<plan>")
    @login_required
    def checkout(plan: str):
        # Free plan does not use Stripe
        if plan == "free":
            current_user.plan = "free"
            db.session.commit()
            return redirect(url_for("index"))

        session = create_checkout_session(plan=plan, user=current_user)
        if session is None:
            flash("Stripe設定が未完了です。環境変数を確認してください。")
            return redirect(url_for("pricing"))
        return redirect(session.url, code=303)

    @app.post("/stripe/webhook")
    def stripe_webhook():
        return handle_webhook(request)

    # ---- App main ----
    @app.route("/", methods=["GET", "POST"])
    @login_required
    def index():
        if request.method == "GET":
            # show input
            return render_template("input.html")

        # Quota check
        if not current_user.can_eval():
            # Free or quota-limited user: block and show upgrade modal
            return render_template("upgrade.html", plan=current_user.plan)

        # Collect inputs
        form = request.form
        # Required (UI enforces)
        payload = {
            "sire": form.get("sire", ""),
            "dam": form.get("dam", ""),
            "damsire": form.get("damsire", ""),
            "dob": form.get("dob", ""),
            "sex": form.get("sex", ""),
            "coat": form.get("coat", ""),
            # Optional
            "body_weight": form.get("body_weight", ""),
            "height": form.get("height", ""),
            "girth": form.get("girth", ""),
            "cannon": form.get("cannon", ""),
            "notes": form.get("notes", ""),
        }

        # Market optional inputs
        market_inputs = {
            "sire_fee_median": form.get("sire_fee_median", ""),
            "dam_value": form.get("dam_value", ""),
            "blacktype_count": form.get("blacktype_count", ""),
            "nearby_gsw": form.get("nearby_gsw", ""),
        }

        # Files
        def save_upload(file_storage, suffix: str) -> str | None:
            if not file_storage or not getattr(file_storage, "filename", ""):
                return None
            name = f"{int(datetime.utcnow().timestamp())}_{current_user.id}_{suffix}"
            ext = Path(file_storage.filename).suffix.lower()[:10] or ".bin"
            out = UPLOAD_DIR / f"{name}{ext}"
            file_storage.save(out)
            return str(out.relative_to(APP_DIR))

        side_path = save_upload(request.files.get("side_photo"), "side")
        front_path = save_upload(request.files.get("front_photo"), "front")
        rear_path = save_upload(request.files.get("rear_photo"), "rear")
        video_path = save_upload(request.files.get("video"), "video")

        # Evaluate
        scores = evaluate_horse(payload=payload, side_photo_rel=side_path, video_rel=video_path)
        market = estimate_market(payload=payload, market_inputs=market_inputs)

        # 3yo prediction image: based on side photo (if missing, None)
        pred_rel = None
        if side_path:
            pred_rel = make_3yo_prediction_image(side_photo_rel=side_path, coat=payload.get("coat", ""))

        result = {
            "scores": scores,
            "market": market,
            "inputs_used": {
                "has_side_photo": bool(side_path),
                "has_video": bool(video_path),
                "missing": [k for k, v in payload.items() if not str(v).strip() and k in ("body_weight", "height", "girth", "cannon")],
            },
            "predicted_3yo_rel": pred_rel,
        }

        # Persist
        label = f"{payload.get('sire','')} × {payload.get('dam','')}"
        ev = Evaluation(
            user_id=current_user.id,
            horse_label=label,
            input_json=json.dumps({"payload": payload, "market": market_inputs}, ensure_ascii=False),
            result_json=json.dumps(result, ensure_ascii=False),
            side_photo_path=side_path,
            front_photo_path=front_path,
            rear_photo_path=rear_path,
            video_path=video_path,
            predicted_3yo_path=pred_rel,
        )
        db.session.add(ev)

        # Consume quota
        current_user.consume_eval()
        db.session.commit()

        return render_template("result.html", payload=payload, result=result, label=label)

    @app.get("/history")
    @login_required
    def history():
        current_user.refresh_monthly_counter()

        if current_user.plan == "free":
            used = int(current_user.quota_used_total or 0)
            limit = 1
        else:
            used = int(current_user.quota_used_month or 0)
            limit = current_user.monthly_limit()

        rows = Evaluation.query.filter_by(user_id=current_user.id).order_by(Evaluation.created_at.desc()).limit(50).all()
        items = []
        for r in rows:
            try:
                res = json.loads(r.result_json)
                total = int(res["scores"]["total"]) if isinstance(res.get("scores"), dict) else 0
                rank = (res.get("scores") or {}).get("rank", "-")
                ml = float((res.get("market") or {}).get("yen_low", 0))
                mh = float((res.get("market") or {}).get("yen_high", 0))
            except Exception:
                total, rank, ml, mh = 0, "-", 0, 0
            items.append(
                {
                    "id": r.id,
                    "created_at": r.created_at,
                    "horse_label": r.horse_label,
                    "total": total,
                    "rank": rank,
                    "market_low": ml,
                    "market_high": mh,
                }
            )

        return render_template("history.html", items=items, used=used, limit=limit)

    @app.get("/e/<int:eval_id>")
    @login_required
    def view_evaluation(eval_id: int):
        r = Evaluation.query.filter_by(id=eval_id, user_id=current_user.id).first_or_404()
        data = json.loads(r.input_json)
        payload = data.get("payload") or {}
        result = json.loads(r.result_json)
        label = r.horse_label
        return render_template("result.html", payload=payload, result=result, label=label)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
