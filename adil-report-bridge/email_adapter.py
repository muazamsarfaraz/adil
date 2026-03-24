"""Email adapter for report submission via SendGrid.

Sends structured incident reports as formatted emails to organisations
that accept reports via email but don't have web forms.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "noreply@mcbx.app")
SENDER_NAME = os.getenv("SENDER_NAME", "AskAdil — MCB Platform")


def _build_email_body(target_config: dict[str, Any], data: dict[str, Any]) -> str:
    """Build a structured plain-text email body from the target config and form data."""
    lines = [
        "--- INCIDENT REPORT ---",
        f"Submitted via AskAdil (askadil.org) on {datetime.now(UTC).strftime('%d %B %Y at %H:%M UTC')}",
        f"Target Organisation: {target_config['name']}",
        "",
    ]

    # Reporter details (if present)
    if data.get("first_name") and data.get("first_name") != "Anonymous":
        lines.append("REPORTER DETAILS:")
        lines.append(f"  Name: {data.get('first_name', '')} {data.get('surname', '')}")
        if data.get("email"):
            lines.append(f"  Email: {data['email']}")
        if data.get("phone"):
            lines.append(f"  Phone: {data['phone']}")
        lines.append("")

    # Incident details
    lines.append("INCIDENT DETAILS:")
    if data.get("incident_details"):
        lines.append(f"  {data['incident_details']}")
    if data.get("incident_summary"):
        lines.append(f"  Summary: {data['incident_summary']}")
    lines.append("")

    if data.get("location"):
        lines.append(f"LOCATION: {data['location']}")
    if data.get("date_time"):
        lines.append(f"DATE/TIME: {data['date_time']}")
    if data.get("suspect_description"):
        lines.append(f"SUSPECT DESCRIPTION: {data['suspect_description']}")

    lines.append("")
    lines.append("--- END REPORT ---")
    lines.append("")
    lines.append(
        "This report was submitted via AskAdil (askadil.org), a free legal education tool "
        "operated by the Muslim Council of Britain. The reporter consented to this submission."
    )

    return "\n".join(lines)


def _build_html_body(target_config: dict[str, Any], data: dict[str, Any]) -> str:
    """Build a formatted HTML email body."""
    timestamp = datetime.now(UTC).strftime("%d %B %Y at %H:%M UTC")

    html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background-color: #1b5e20; color: white; padding: 16px 24px; border-radius: 8px 8px 0 0;">
        <h2 style="margin: 0;">Incident Report</h2>
        <p style="margin: 4px 0 0; opacity: 0.9; font-size: 14px;">
            Submitted via AskAdil (askadil.org) on {timestamp}
        </p>
    </div>
    <div style="border: 1px solid #ddd; border-top: none; padding: 24px; border-radius: 0 0 8px 8px;">
"""

    # Reporter details
    if data.get("first_name") and data.get("first_name") != "Anonymous":
        html += """
        <h3 style="color: #1b5e20; border-bottom: 1px solid #eee; padding-bottom: 8px;">Reporter Details</h3>
        <table style="width: 100%; border-collapse: collapse;">
"""
        html += f'<tr><td style="padding: 4px 8px; color: #666; width: 120px;">Name:</td><td style="padding: 4px 8px;">{data.get("first_name", "")} {data.get("surname", "")}</td></tr>'
        if data.get("email"):
            html += f'<tr><td style="padding: 4px 8px; color: #666;">Email:</td><td style="padding: 4px 8px;">{data["email"]}</td></tr>'
        if data.get("phone"):
            html += f'<tr><td style="padding: 4px 8px; color: #666;">Phone:</td><td style="padding: 4px 8px;">{data["phone"]}</td></tr>'
        html += "</table>"

    # Incident
    html += '<h3 style="color: #1b5e20; border-bottom: 1px solid #eee; padding-bottom: 8px; margin-top: 20px;">Incident Details</h3>'
    if data.get("incident_details"):
        html += f'<p style="line-height: 1.6;">{data["incident_details"]}</p>'
    if data.get("incident_summary"):
        html += f'<p style="line-height: 1.6;"><strong>Summary:</strong> {data["incident_summary"]}</p>'

    html += '<table style="width: 100%; border-collapse: collapse; margin-top: 12px;">'
    if data.get("location"):
        html += f'<tr><td style="padding: 4px 8px; color: #666; width: 120px;">Location:</td><td style="padding: 4px 8px;">{data["location"]}</td></tr>'
    if data.get("date_time"):
        html += f'<tr><td style="padding: 4px 8px; color: #666;">Date/Time:</td><td style="padding: 4px 8px;">{data["date_time"]}</td></tr>'
    if data.get("suspect_description"):
        html += f'<tr><td style="padding: 4px 8px; color: #666;">Suspect:</td><td style="padding: 4px 8px;">{data["suspect_description"]}</td></tr>'
    html += "</table>"

    html += """
        <hr style="margin: 24px 0; border: none; border-top: 1px solid #eee;">
        <p style="font-size: 12px; color: #999;">
            This report was submitted via <a href="https://askadil.org">AskAdil</a>,
            a free legal education tool operated by the Muslim Council of Britain.
            The reporter consented to this submission.
        </p>
    </div>
</div>
"""
    return html


async def send_email_report(
    target_id: str,
    target_config: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    """Send a structured incident report via SendGrid email.

    Args:
        target_id: Target identifier.
        target_config: Target configuration dict (must include 'email_to').
        data: Flat dict of form field values.

    Returns:
        Dict with success, confirmation_text, etc.
    """
    if not SENDGRID_API_KEY:
        return {
            "success": False,
            "target": target_id,
            "error": "SendGrid API key not configured.",
        }

    recipient = target_config.get("email_to")
    if not recipient:
        return {
            "success": False,
            "target": target_id,
            "error": f"No email recipient configured for target '{target_id}'.",
        }

    subject = target_config.get("email_subject", f"Incident Report via AskAdil — {target_config['name']}")

    plain_body = _build_email_body(target_config, data)
    html_body = _build_html_body(target_config, data)

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Content, Email, Mail, MimeType, To

        message = Mail(
            from_email=Email(SENDER_EMAIL, SENDER_NAME),
            to_emails=To(recipient),
            subject=subject,
        )
        message.add_content(Content(MimeType.text, plain_body))
        message.add_content(Content(MimeType.html, html_body))

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        if response.status_code in (200, 201, 202):
            logger.info(
                "Email report sent: target=%s recipient=%s status=%s",
                target_id,
                recipient,
                response.status_code,
            )
            return {
                "success": True,
                "target": target_id,
                "confirmation_text": (
                    f"Your incident report has been emailed to {target_config['name']} "
                    f"at {recipient}. They may contact you if you provided your details."
                ),
                "submitted_at": datetime.now(UTC).isoformat(),
            }
        else:
            logger.error(
                "Email send failed: target=%s status=%s",
                target_id,
                response.status_code,
            )
            return {
                "success": False,
                "target": target_id,
                "error": f"Email delivery failed (status {response.status_code}).",
            }

    except Exception as e:
        logger.error("Email adapter error for target=%s: %s", target_id, e)
        return {
            "success": False,
            "target": target_id,
            "error": f"Failed to send email report: {str(e)}",
        }
    finally:
        del data
