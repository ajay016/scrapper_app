from pyvirtualdisplay import Display
from playwright.sync_api import sync_playwright
from contextlib import contextmanager
import platform

# Detect if we are on Linux
IS_LINUX = platform.system() == "Linux"

@contextmanager
def virtual_display_if_needed():
    """
    Starts a virtual display on Linux when headless=False is required.
    """
    display = None
    if IS_LINUX:
        display = Display(visible=0, size=(1920, 1080))
        display.start()
    try:
        yield
    finally:
        if display:
            display.stop()

@contextmanager
def playwright_browser(headless=True, **kwargs):
    """
    Context manager for launching Playwright browser with optional virtual display.

    Usage:
        with playwright_browser(headless=False) as browser:
            page = browser.new_page()
            ...
    """
    with virtual_display_if_needed():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, **kwargs)
            try:
                yield browser
            finally:
                browser.close()