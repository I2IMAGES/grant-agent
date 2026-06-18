import os
import logging
from datetime import date
from pathlib import Path
import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

ELIGIBILITY_GROUPS = ["MINORITY-OWNED", "WOMEN-OWNED", "HUBZONE", "PARTNERSHIP"]
TEMPLATE_DIR = Path(__file__).parent / "templates"


def _group_grants(grants: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {g: [] for g in ELIGIBILITY_GROUPS}
    seen_urls: set[str] = set()
    for grant in grants:
        tags = grant.get("eligibility", [])
        url = grant.get("url", "")
        for tag in ELIGIBILITY_GROUPS:
            if tag in tags:
                if url not in seen_urls:
                    seen_urls.add(url)
                    groups[tag].append(grant)
                break
    return groups


def send(grants: list[dict], sources_checked: int = 0, note: str = "", filter_failed: bool = False) -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]
    recipient = os.environ["RECIPIENT_EMAIL"]
    today_str = date.today().strftime("%B %d, %Y")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("digest.html")

    grouped = _group_grants(grants)
    html = template.render(
        grants=grants,
        grouped=grouped,
        eligibility_groups=ELIGIBILITY_GROUPS,
        date=today_str,
        sources_checked=sources_checked,
        note=note,
        filter_failed=filter_failed,
    )

    subject = "Grant Digest - {} New Opportunities - {}".format(len(grants), today_str)

    params: resend.Emails.SendParams = {
        "from": "grants@inward2onward.com",
        "to": [recipient],
        "subject": subject,
        "html": html,
    }
    resend.Emails.send(params)
    logger.info("emailer: sent digest to %s (%d grants)", recipient, len(grants))


def send_no_new_grants() -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]
    recipient = os.environ["RECIPIENT_EMAIL"]
    today_str = date.today().strftime("%B %d, %Y")

    html = (
        "<html><body style=\"font-family:sans-serif;color:#475569;padding:2rem;\">"
        "<h2 style=\"color:#1E293B;\">INWARD2ONWARD | Daily Grant Digest | {}</h2>"
        "<p>No new grant opportunities were found today that haven't been seen in the last 30 days.</p>"
        "<p style=\"font-size:0.85rem;color:#94a3b8;\">"
        "Inward2Onward LLC - Glendale, AZ - 623.272.8066 - ej@inward2onward.com"
        "</p></body></html>"
    ).format(today_str)

    params: resend.Emails.SendParams = {
        "from": "grants@inward2onward.com",
        "to": [recipient],
        "subject": "Grant Digest - No New Results - {}".format(today_str),
        "html": html,
    }
    resend.Emails.send(params)
    logger.info("emailer: sent no-new-grants notice to %s", recipient)
