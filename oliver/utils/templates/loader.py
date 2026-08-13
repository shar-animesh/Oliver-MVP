"""Render Oliver's fixed Siemens Energy email shell."""

from importlib.resources import files
from typing import Optional

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

# Load the packaged Siemens Energy logo once when this module is imported. The
# source file contains only base64 text; strip() removes its file-ending newline
# before the data-URI prefix is added.
_LOGO_DATA_URI = "data:image/png;base64," + (
    files("utils.templates").joinpath("assets/siemens-energy-logo.png.b64").read_text(encoding="ascii").strip()
)

_environment = Environment(
    # Locate the email templates inside the installed utils Python package.
    # This works both from the repository and from an installed wheel without a
    # machine-specific filesystem path.
    loader=PackageLoader("utils", "templates"),
    # Automatically HTML-escape ordinary values rendered into files ending in
    # .html. This protects values such as subject and preheader from being
    # interpreted as markup.
    autoescape=select_autoescape(enabled_extensions=("html",)),
    # Raise an error if the template references a variable that the caller did
    # not supply, instead of silently rendering the missing value as an empty
    # string.
    undefined=StrictUndefined,
    # Remove the first newline after Jinja block tags such as {% if %}. This
    # prevents template control flow from adding unnecessary blank lines.
    trim_blocks=True,
    # Remove spaces and tabs before Jinja block tags so template indentation
    # does not create unwanted whitespace in the generated HTML.
    lstrip_blocks=True,
    # Do not preserve the template file's final newline in the rendered email.
    keep_trailing_newline=False,
)


def render_oliver_email(
    *,
    subject: str,
    content_html: str,
    preheader: Optional[str] = None,
) -> str:
    """Place the model-generated fragment inside the fixed brand shell."""
    return _environment.get_template("oliver-email.jinja2.html").render(
        subject=subject.strip(),
        preheader=(preheader or subject).strip(),
        logo_data_uri=_LOGO_DATA_URI,
        # The system prompt instructs Oliver to return an HTML fragment. Markup
        # tells Jinja that this one value is intentional HTML and must not be
        # escaped; all ordinary template values remain autoescaped.
        content_html=Markup(content_html),
    )
