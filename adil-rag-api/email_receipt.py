"""Email receipt sender for report submissions.

Sends a confirmation email to the user after a successful report submission.
Uses SendGrid. Never includes PII beyond the user's own email address.
"""
import os
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "noreply@mcbx.app")
SENDER_NAME = os.getenv("SENDER_NAME", "AskAdil — MCB Platform")


async def send_receipt(
    to_email: str,
    target_name: str,
    reference_number: Optional[str],
    incident_summary: str,
    submitted_at: Optional[str] = None,
):
    """Send a confirmation receipt email to the user after report submission.

    Args:
        to_email: User's email address (collected during PII flow).
        target_name: Display name of the target organisation.
        reference_number: Reference number from the submission (if any).
        incident_summary: Brief incident description (from conversation, no PII).
        submitted_at: ISO timestamp of submission.
    """
    if not SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY not set — skipping receipt email")
        return

    if not to_email or "@" not in to_email:
        logger.warning("Invalid email for receipt — skipping")
        return

    ref_display = reference_number or "Not provided"
    timestamp = submitted_at or datetime.now(timezone.utc).isoformat()
    # Truncate incident summary to avoid leaking too much
    summary_short = incident_summary[:300] + "..." if len(incident_summary) > 300 else incident_summary

    subject = f"AskAdil — Your report to {target_name} has been submitted"

    plain_body = f"""Your report has been submitted

Reference Number: {ref_display}
Submitted to: {target_name}
Date: {timestamp}

INCIDENT SUMMARY:
{summary_short}

IMPORTANT — SAVE THIS EMAIL
This is your confirmation that a report was submitted on your behalf via AskAdil.
AskAdil does not store your personal information after submission.
If you need to follow up, quote your reference number above.

WHAT HAPPENS NEXT:
- {target_name} will review your report
- They may contact you at the email or phone number you provided
- If you don't hear back within 7 days, you can follow up directly
- For police reports: call 101 and quote your reference number

NEED MORE HELP?
- Tell MAMA: tellmamauk.org — Report anti-Muslim hate
- IRU: theiru.org.uk — Phone: 020 3904 6555
- Citizens Advice: citizensadvice.org.uk
- Find a solicitor: solicitors.lawsociety.org.uk

---
AskAdil (askadil.org) — Educate First, Litigate Second
A Muslim Council of Britain initiative
This is an automated email. AskAdil is an educational tool, not a law firm.
"""

    html_body = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background-color: #1b5e20; color: white; padding: 20px 24px; border-radius: 8px 8px 0 0;">
        <h1 style="margin: 0; font-size: 22px;">Your report has been submitted</h1>
        <p style="margin: 8px 0 0; opacity: 0.9; font-size: 14px;">AskAdil — Educate First, Litigate Second</p>
    </div>

    <div style="border: 1px solid #ddd; border-top: none; padding: 24px; border-radius: 0 0 8px 8px;">

        <div style="background-color: #e8f5e9; border-left: 4px solid #1b5e20; padding: 16px; margin-bottom: 20px; border-radius: 4px;">
            <p style="margin: 0; font-size: 18px; font-weight: bold;">Reference Number: {ref_display}</p>
            <p style="margin: 8px 0 0; color: #555;">Submitted to: {target_name}</p>
            <p style="margin: 4px 0 0; color: #555; font-size: 13px;">Date: {timestamp}</p>
        </div>

        <h3 style="color: #1b5e20; border-bottom: 1px solid #eee; padding-bottom: 8px;">Incident Summary</h3>
        <p style="line-height: 1.6; color: #333;">{summary_short}</p>

        <div style="background-color: #fff3e0; border-left: 4px solid #e65100; padding: 16px; margin: 20px 0; border-radius: 4px;">
            <p style="margin: 0; font-weight: bold; color: #e65100;">Important — Save this email</p>
            <p style="margin: 8px 0 0; font-size: 14px;">
                This is your confirmation that a report was submitted on your behalf.
                AskAdil does not store your personal information after submission.
                If you need to follow up, quote your reference number above.
            </p>
        </div>

        <h3 style="color: #1b5e20; border-bottom: 1px solid #eee; padding-bottom: 8px;">What happens next</h3>
        <ul style="line-height: 1.8; color: #333;">
            <li><strong>{target_name}</strong> will review your report</li>
            <li>They may contact you at the email or phone number you provided</li>
            <li>If you don't hear back within 7 days, you can follow up directly</li>
            <li>For police reports: call <strong>101</strong> and quote your reference number</li>
        </ul>

        <h3 style="color: #1b5e20; border-bottom: 1px solid #eee; padding-bottom: 8px;">Need more help?</h3>
        <ul style="line-height: 1.8;">
            <li><a href="https://tellmamauk.org" style="color: #1b5e20;">Tell MAMA</a> — Report anti-Muslim hate</li>
            <li><a href="https://theiru.org.uk" style="color: #1b5e20;">IRU</a> — Phone: 020 3904 6555</li>
            <li><a href="https://citizensadvice.org.uk" style="color: #1b5e20;">Citizens Advice</a> — Free legal guidance</li>
            <li><a href="https://solicitors.lawsociety.org.uk" style="color: #1b5e20;">Find a Solicitor</a> — Law Society directory</li>
        </ul>

        <hr style="margin: 24px 0; border: none; border-top: 1px solid #eee;">
        <p style="font-size: 12px; color: #999; text-align: center;">
            <a href="https://askadil.org" style="color: #999;">AskAdil</a> — A Muslim Council of Britain initiative<br>
            This is an automated email. AskAdil is an educational tool, not a law firm.
        </p>
    </div>
</div>
"""

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Email, To, Content, MimeType

        message = Mail(
            from_email=Email(SENDER_EMAIL, SENDER_NAME),
            to_emails=To(to_email),
            subject=subject,
        )
        message.add_content(Content(MimeType.text, plain_body))
        message.add_content(Content(MimeType.html, html_body))

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        if response.status_code in (200, 201, 202):
            logger.info("Receipt email sent to user for target=%s", target_name)
        else:
            logger.error("Receipt email failed: status=%s", response.status_code)

    except Exception as e:
        # Never let receipt failure block the response
        logger.error("Receipt email error: %s", e)
