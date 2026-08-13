# Path: utils/prompts/loader.py
# Description: Build the single Oliver system prompt.

from jinja2 import Environment, PackageLoader, StrictUndefined

_environment = Environment(
    # Locate the prompts directory inside the installed utils Python package.
    # This works both from the repository and after installing a wheel, without
    # depending on a machine-specific filesystem path.
    loader=PackageLoader("utils", "prompts"),
    # The rendered result is a plain-text model prompt, not an HTML document.
    # Disabling autoescaping preserves characters in the email thread exactly
    # instead of converting them into HTML entities.
    autoescape=False,
    # Raise an error if the template references a variable that was not passed
    # by the caller. This prevents missing values from silently rendering as
    # empty strings inside Oliver's system prompt.
    undefined=StrictUndefined,
    # Remove the first newline after Jinja block tags such as {% if %}. This
    # avoids unwanted blank lines if control blocks are added to the prompt.
    trim_blocks=True,
    # Remove spaces and tabs before Jinja block tags. This keeps template
    # control-flow indentation from leaking into the rendered prompt.
    lstrip_blocks=True,
    # Do not preserve the template file's final newline in the built prompt.
    keep_trailing_newline=False,
)


def build_system_prompt(email_thread: str) -> str:
    """Build the system prompt with the current email thread."""
    return _environment.get_template("system-prompt.jinja2").render(email_thread=email_thread)
