"""Shared Jinja2 templates instance with global filters."""
from fastapi.templating import Jinja2Templates
from app.i18n import t as translate_fn, SUPPORTED_LANGUAGES
from app.permissions import can_view, can_edit, can_delete, has_any_access

templates = Jinja2Templates(directory="app/templates")


def fmt_eur(val):
    """Format number as French EUR: 1.234,56"""
    if val is None:
        return "0"
    neg = val < 0
    val = abs(val)
    if val == int(val):
        s = f"{int(val):,}".replace(",", ".")
    else:
        s = f"{val:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"-{s}" if neg else s


def fmt_eur_int(val):
    """Format number as French EUR without decimals: 1.234"""
    if val is None:
        return "0"
    neg = val < 0
    val = abs(int(val))
    s = f"{val:,}".replace(",", ".")
    return f"-{s}" if neg else s


def country_flag(country_code):
    """Convert 2-letter country code to flag emoji. FR -> 🇫🇷"""
    if not country_code or len(country_code) != 2:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in country_code.upper())


# Register global filters
templates.env.filters["eur"] = fmt_eur
templates.env.filters["eur_int"] = fmt_eur_int
templates.env.filters["flag"] = country_flag

# Register i18n globals (accessible in all templates)
templates.env.globals["t"] = translate_fn
templates.env.globals["SUPPORTED_LANGUAGES"] = SUPPORTED_LANGUAGES

# Register permission helpers
templates.env.globals["can_view"] = can_view
templates.env.globals["can_edit"] = can_edit
templates.env.globals["can_delete"] = can_delete
templates.env.globals["has_any_access"] = has_any_access
