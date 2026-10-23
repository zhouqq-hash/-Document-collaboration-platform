"""Browser smoke test for explicit manual fallback when AI is unavailable."""

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def browser_executable():
    configured = os.environ.get("BROWSER_EXECUTABLE")
    if configured:
        return configured
    candidates = (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    )
    return next((path for path in candidates if Path(path).exists()), None)


with sync_playwright() as playwright:
    launch_options = {"headless": True}
    if browser_executable():
        launch_options["executable_path"] = browser_executable()
    browser = playwright.chromium.launch(**launch_options)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    console_errors = []
    page.on(
        "console",
        lambda message: (
            console_errors.append(message.text)
            if message.type == "error"
            else None
        ),
    )

    page.goto("http://127.0.0.1:5055/documents/index.html")
    page.wait_for_load_state("networkidle")
    assert page.locator("#username").input_value() == ""
    assert page.locator("#password").input_value() == ""
    assert page.locator("#demoCredentials").is_hidden()
    login_result = page.evaluate(
        """async () => {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    username: 'admin',
                    password: 'admin12345678'
                })
            });
            return {status: response.status, body: await response.text()};
        }"""
    )
    assert login_result["status"] == 200

    page.goto("http://127.0.0.1:5055/documents/document-detail.html?id=1")
    page.wait_for_load_state("networkidle")
    page.locator("#aiReviewButton").click()
    page.locator("#humanReviewNote").wait_for()
    page.screenshot(
        path="testdata/ai-fallback-before.png", full_page=True
    )

    page.locator("#humanReviewNote").fill(
        "已逐项对照教学大纲模板完成人工核验"
    )
    page.locator('[data-human-decision="pass"]').click()
    page.locator("[data-confirm-pass]").click()
    page.get_by_text("已通过", exact=True).first.wait_for()
    page.screenshot(
        path="testdata/ai-fallback-after.png", full_page=True
    )

    result = page.evaluate(
        """async () => {
            const response = await fetch('/api/documents/1');
            return response.json();
        }"""
    )
    data = result["data"]
    assert data["review_state"]["code"] == "approved"
    unexpected_errors = [
        message
        for message in console_errors
        if "status of 401" not in message
        and "status of 503" not in message
    ]
    assert not unexpected_errors, unexpected_errors
    print(
        json.dumps(
            {
                "review_state": data["review_state"],
                "console_errors": unexpected_errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    browser.close()
