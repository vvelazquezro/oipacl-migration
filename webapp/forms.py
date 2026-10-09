from email_validator import EmailNotValidError, validate_email
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional, Regexp, ValidationError

_ACCOUNT_KEY_RE = r"^[A-Za-z0-9:\-_]{1,64}$"


class CredentialsForm(FlaskForm):
    host = StringField("EdgeGrid Host", validators=[DataRequired(), Length(max=255)])
    client_token = PasswordField("Client Token", validators=[DataRequired(), Length(max=255)])
    client_secret = PasswordField("Client Secret", validators=[DataRequired(), Length(max=255)])
    access_token = PasswordField("Access Token", validators=[DataRequired(), Length(max=255)])


class AccountSwitchKeyForm(FlaskForm):
    # Selected after connecting (top-right corner), not part of the initial "Connect to Akamai" form.
    account_switch_key = StringField("Account Switch Key", validators=[Optional(), Regexp(_ACCOUNT_KEY_RE, message="Invalid account switch key format")])


class PropertyListForm(FlaskForm):
    properties_file = FileField("Upload CSV", validators=[Optional(), FileAllowed(["csv", "txt"], "CSV or text files only")])
    properties_text = TextAreaField("Or paste property names (one per line)", validators=[Optional()])
    environment = SelectField("Environment", choices=[("production", "Production"), ("staging", "Staging"), ("latest", "Latest")],
                               validators=[DataRequired()])


class AuditForm(PropertyListForm):
    pass


class _NotifyEmailMixin:
    """Shared "notify email(s)" validation for forms that can trigger an activation."""

    def _validate_notify_addresses(self, value):
        addresses = [a.strip() for a in (value or "").split(",") if a.strip()]
        if not addresses:
            raise ValidationError("Provide at least one email address.")
        invalid = []
        for address in addresses:
            try:
                validate_email(address, check_deliverability=False)
            except EmailNotValidError:
                invalid.append(address)
        if invalid:
            raise ValidationError(f"Invalid email address(es): {', '.join(invalid)}")


class MigrateForm(PropertyListForm, _NotifyEmailMixin):
    notes = StringField("Notes", default="SiteShield Migration to OIPACL", validators=[Optional(), Length(max=500)])
    enable_tiered_distribution = BooleanField(
        "Enable Tiered Distribution (second layer of caching)", default=True, validators=[Optional()],
    )
    add_oipacl_without_siteshield = BooleanField(
        "Still add OriginIpAcl when SiteShield is not present", default=True, validators=[Optional()],
    )
    activate_option = SelectField(
        "Activate after migration",
        choices=[
            ("none", "Do not activate (default)"),
            ("staging", "Push to staging"),
            ("production", "Push to production"),
            ("both", "Push both networks"),
        ],
        default="none", validators=[DataRequired()],
    )
    notify_email = StringField("Notify Email(s) (comma-separated for multiple)", validators=[Optional(), Length(max=1000)])
    peer_reviewer_email = StringField("Peer Reviewer Email (required for production)", validators=[Optional(), Email(), Length(max=255)])

    def validate_notify_email(self, field):
        if self.activate_option.data == "none":
            return
        self._validate_notify_addresses(field.data)

    def validate_peer_reviewer_email(self, field):
        if self.activate_option.data in ("production", "both") and not field.data:
            raise ValidationError("Peer reviewer email is required when activating to production.")


class ActivateForm(FlaskForm, _NotifyEmailMixin):
    activation_file = FileField("Upload activation CSV (name,version)", validators=[Optional(), FileAllowed(["csv", "txt"], "CSV or text files only")])
    activation_text = TextAreaField("Or paste rows as name,version (one per line)", validators=[Optional()])
    environment = SelectField("Network", choices=[("staging", "Staging"), ("production", "Production")], validators=[DataRequired()])
    notes = StringField("Notes", default="SiteShield Migration to OIPACL", validators=[Optional(), Length(max=500)])
    notify_email = StringField("Notify Email(s) (comma-separated for multiple)", validators=[DataRequired(), Length(max=1000)])
    peer_reviewer_email = StringField("Peer Reviewer Email (required for production)", validators=[Optional(), Email(), Length(max=255)])

    def validate_notify_email(self, field):
        self._validate_notify_addresses(field.data)

    def validate_peer_reviewer_email(self, field):
        if self.environment.data == "production" and not field.data:
            raise ValidationError("Peer reviewer email is required when activating to production.")
