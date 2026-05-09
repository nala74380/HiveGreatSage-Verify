"""Browser-use login/logout test script."""
import asyncio

from browser_use import Browser


async def main():
    b = Browser()
    page = await b.get_current_page()

    # Login
    await page.locator("input[placeholder='用户名']").fill("admin")
    await page.locator("input[placeholder='密码']").fill("admin123")
    await page.locator("button").click()

    # Wait for dashboard
    await page.wait_for_timeout(3000)

    # Verify we're on dashboard (URL should not be /login)
    url = page.url
    print(f"After login URL: {url}")
    assert "/login" not in url, "Login failed - still on login page"

    # Take screenshot
    await page.screenshot(path="E:/Hive-GreatSage/dashboard_after_login.png")
    print("Dashboard screenshot saved")

    # Logout - click the dropdown trigger (the username element)
    await page.locator(".user-info").click()
    await page.wait_for_timeout(500)

    # Click logout item
    await page.locator(".el-dropdown-menu__item:has-text('退出登录')").click()
    await page.wait_for_timeout(500)

    # Confirm dialog
    await page.locator(".el-message-box__btns button:has-text('退出')").click()
    await page.wait_for_timeout(3000)

    # Verify redirected to login
    url = page.url
    print(f"After logout URL: {url}")
    assert "/login" in url or "/login?" in url, f"Logout failed - not on login page: {url}"

    await page.screenshot(path="E:/Hive-GreatSage/login_after_logout.png")
    print("Logout screenshot saved")
    print("Test PASSED: Login and logout flow works correctly")


if __name__ == "__main__":
    asyncio.run(main())
