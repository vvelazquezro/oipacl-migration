from flask import Blueprint, abort, current_app, g, redirect, render_template, session, url_for
from flask import Response, jsonify, stream_with_context

from akamai_core.csv_utils import parse_activation_rows, parse_property_rows, rows_to_csv_bytes

from .forms import AccountSwitchKeyForm, ActivateForm, AuditForm, CredentialsForm, MigrateForm
from .jobs import stream_job_logs

bp = Blueprint("main", __name__)


def _read_upload_or_text(file_storage, text_value):
    if file_storage and file_storage.filename:
        return file_storage.read().decode("utf-8", errors="replace")
    return text_value or ""


def _creds_from_form(form):
    return {
        "host": form.host.data.strip(),
        "client_token": form.client_token.data.strip(),
        "client_secret": form.client_secret.data.strip(),
        "access_token": form.access_token.data.strip(),
    }


@bp.before_request
def _load_credentials_state():
    g.creds = current_app.cred_store.get(session.get("cred_id"))
    g.has_credentials = g.creds is not None
    g.has_account_key = bool((g.creds or {}).get("account_switch_key"))
    g.is_ready = g.has_credentials and g.has_account_key


@bp.context_processor
def _inject_credentials_state():
    account_switch_key = (getattr(g, "creds", None) or {}).get("account_switch_key", "")
    return {
        "has_credentials": getattr(g, "has_credentials", False),
        "has_account_key": getattr(g, "has_account_key", False),
        "is_ready": getattr(g, "is_ready", False),
        "creds_form": CredentialsForm(),
        "account_key_form": AccountSwitchKeyForm(account_switch_key=account_switch_key),
    }


@bp.route("/credentials", methods=["POST"])
def save_credentials():
    form = CredentialsForm()
    if not form.validate_on_submit():
        return jsonify({"ok": False, "errors": form.errors}), 400
    # Preserve an already-selected account switch key across a "change credentials" re-submit.
    creds = _creds_from_form(form)
    creds["account_switch_key"] = (g.creds or {}).get("account_switch_key", "")
    session["cred_id"] = current_app.cred_store.put(creds)
    session.permanent = True
    return jsonify({"ok": True})


@bp.route("/credentials/account-key", methods=["POST"])
def update_account_key():
    if not g.has_credentials:
        return jsonify({"ok": False, "errors": {"account_switch_key": ["Connect your Akamai credentials first."]}}), 400
    form = AccountSwitchKeyForm()
    if not form.validate_on_submit():
        return jsonify({"ok": False, "errors": form.errors}), 400
    current_app.cred_store.update(session.get("cred_id"), {"account_switch_key": (form.account_switch_key.data or "").strip()})
    return jsonify({"ok": True})


@bp.route("/credentials/clear", methods=["POST"])
def clear_credentials():
    current_app.cred_store.clear(session.pop("cred_id", None))
    return redirect(url_for("main.index"))


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/audit", methods=["GET", "POST"])
def audit():
    if not g.is_ready:
        return redirect(url_for("main.index"))
    form = AuditForm()
    if form.validate_on_submit():
        creds = current_app.cred_store.get(session.get("cred_id"))
        if not creds:
            form.properties_text.errors.append("Please connect your Akamai credentials first.")
        else:
            raw_text = _read_upload_or_text(form.properties_file.data, form.properties_text.data)
            names = parse_property_rows(raw_text)
            max_props = current_app.config["MAX_PROPERTIES_PER_JOB"]
            if not names:
                form.properties_text.errors.append("Provide at least one property name (upload or paste).")
            elif len(names) > max_props:
                form.properties_text.errors.append(f"Too many properties ({len(names)}); limit is {max_props}.")
            else:
                job_id = current_app.job_manager.submit(
                    "audit", creds,
                    {"names": names, "version": form.environment.data, "account_key": creds.get("account_switch_key", "")},
                )
                return redirect(url_for("main.job_view", job_id=job_id))
    return render_template("job_form.html", form=form, action="audit", title="Audit Properties")


@bp.route("/migrate", methods=["GET", "POST"])
def migrate():
    if not g.is_ready:
        return redirect(url_for("main.index"))
    form = MigrateForm()
    if form.validate_on_submit():
        creds = current_app.cred_store.get(session.get("cred_id"))
        if not creds:
            form.properties_text.errors.append("Please connect your Akamai credentials first.")
        else:
            raw_text = _read_upload_or_text(form.properties_file.data, form.properties_text.data)
            names = parse_property_rows(raw_text)
            max_props = current_app.config["MAX_PROPERTIES_PER_JOB"]
            if not names:
                form.properties_text.errors.append("Provide at least one property name (upload or paste).")
            elif len(names) > max_props:
                form.properties_text.errors.append(f"Too many properties ({len(names)}); limit is {max_props}.")
            else:
                job_id = current_app.job_manager.submit(
                    "migrate", creds,
                    {
                        "names": names, "version": form.environment.data,
                        "account_key": creds.get("account_switch_key", ""), "notes": form.notes.data or "SiteShield Migration to OIPACL",
                        "enable_td": form.enable_tiered_distribution.data,
                        "add_oipacl_without_ss": form.add_oipacl_without_siteshield.data,
                    },
                )
                return redirect(url_for("main.job_view", job_id=job_id))
    return render_template("job_form.html", form=form, action="migrate", title="Migrate Properties")


@bp.route("/activate", methods=["GET", "POST"])
def activate():
    if not g.is_ready:
        return redirect(url_for("main.index"))
    form = ActivateForm()
    if form.validate_on_submit():
        creds = current_app.cred_store.get(session.get("cred_id"))
        if not creds:
            form.activation_text.errors.append("Please connect your Akamai credentials first.")
        else:
            raw_text = _read_upload_or_text(form.activation_file.data, form.activation_text.data)
            rows = parse_activation_rows(raw_text)
            max_props = current_app.config["MAX_PROPERTIES_PER_JOB"]
            if not rows:
                form.activation_text.errors.append("Provide at least one 'name,version' row (upload or paste).")
            elif len(rows) > max_props:
                form.activation_text.errors.append(f"Too many rows ({len(rows)}); limit is {max_props}.")
            else:
                notes = form.notes.data or "SiteShield Migration to OIPACL"
                if form.jira_link.data:
                    notes = f"{notes} | {form.jira_link.data.strip()}"
                job_id = current_app.job_manager.submit(
                    "activate", creds,
                    {
                        "rows": rows, "version": form.environment.data,
                        "account_key": creds.get("account_switch_key", ""), "notes": notes,
                        "notify_email": form.notify_email.data.strip(),
                        "peer_reviewer_email": (form.peer_reviewer_email.data or "").strip(),
                    },
                )
                return redirect(url_for("main.job_view", job_id=job_id))
    return render_template("job_form.html", form=form, action="activate", title="Activate Properties")


@bp.route("/jobs/<job_id>")
def job_view(job_id):
    job = current_app.job_manager.get(job_id)
    if not job:
        abort(404)
    return render_template("job.html", job=job)


@bp.route("/jobs/<job_id>/stream")
def job_stream(job_id):
    job = current_app.job_manager.get(job_id)
    if not job:
        abort(404)

    resp = Response(stream_with_context(stream_job_logs(job)), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@bp.route("/jobs/<job_id>/files")
def job_files(job_id):
    job = current_app.job_manager.get(job_id)
    if not job:
        abort(404)
    return jsonify({
        "status": job.status, "error": job.error,
        "files": sorted((job.files or {}).keys()), "charts": job.charts,
        "names": job.names or [],
        "pending_networks": job.pending_networks or [],
        "migrated_filename": job.migrated_filename,
        "property_links": job.property_links or [],
    })


@bp.route("/jobs/<job_id>/download/<path:filename>")
def job_download(job_id, filename):
    job = current_app.job_manager.get(job_id)
    if not job or not job.files or filename not in job.files:
        abort(404)
    headers, rows = job.files[filename]
    data = rows_to_csv_bytes(headers, rows)
    resp = Response(data, mimetype="text/csv")
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


@bp.route("/jobs/<job_id>/log")
def job_download_log(job_id):
    job = current_app.job_manager.get(job_id)
    if not job:
        abort(404)
    data = "\n".join(job.log_lines).encode("utf-8")
    resp = Response(data, mimetype="text/plain")
    resp.headers["Content-Disposition"] = f"attachment; filename={job.action}_{job_id}.log"
    return resp
