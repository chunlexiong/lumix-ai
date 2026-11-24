import ipaddress
import socket
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


VIEWPORT_WIDTH = 1100
VIEWPORT_HEIGHT = 795
SCREENSHOT_TIMEOUT_MS = 15_000
RENDER_WAIT_MS = 1_000


def _validate_public_http_url(url):
    """Reject non-web and non-public destinations before the browser visits them."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Project previews require a public HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("Project preview URLs cannot contain credentials.")

    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("Project preview host could not be resolved.") from exc

    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Project previews can only access publicly routable hosts.")


def capture_project_screenshot(url):
    """Render a project page at 2x the gallery's desktop preview size."""
    _validate_public_http_url(url)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                device_scale_factor=2,
            )

            def allow_public_request(route):
                try:
                    _validate_public_http_url(route.request.url)
                except (ValueError, OSError):
                    route.abort()
                else:
                    route.continue_()

            # Apply the same check to redirects, scripts, images, and other requests.
            page.route("**/*", allow_public_request)
            response = page.goto(url, wait_until="domcontentloaded", timeout=SCREENSHOT_TIMEOUT_MS)
            if response and response.status >= 400:
                raise RuntimeError(f"Project page returned HTTP {response.status}.")
            page.wait_for_timeout(RENDER_WAIT_MS)
            return page.screenshot(type="jpeg", quality=88, scale="device")
        finally:
            browser.close()
