"""
ChatGPT Browser Automation Service

Automates the ChatGPT web interface to submit analysis prompts with screenshots
and extract the JSON response.

Requires: playwright, playwright install chromium
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# ChatGPT URLs
CHATGPT_URL = "https://chat.openai.com/"
CHATGPT_NEW_CHAT_URL = "https://chat.openai.com/?model=gpt-4o"

# Cookies file for session persistence
COOKIES_FILE = Path(__file__).parent.parent.parent / "data" / ".chatgpt_cookies.json"


def save_cookies(cookies: List[dict]):
    """Save browser cookies to file for session persistence."""
    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f, indent=2)
    logger.info(f"Saved {len(cookies)} cookies to {COOKIES_FILE}")


def load_cookies() -> Optional[List[dict]]:
    """Load browser cookies from file."""
    if COOKIES_FILE.exists():
        try:
            with open(COOKIES_FILE, "r") as f:
                cookies = json.load(f)
            logger.info(f"Loaded {len(cookies)} cookies from {COOKIES_FILE}")
            return cookies
        except Exception as e:
            logger.warning(f"Failed to load cookies: {e}")
    return None


async def wait_for_login(page, timeout: int = 120):
    """
    Wait for user to complete manual login.
    Detects successful login by checking for the chat input.
    """
    logger.info("Waiting for manual login... (you have 2 minutes)")
    print("\n" + "="*60)
    print("🔐 Please log in to ChatGPT in the browser window")
    print("   The script will continue automatically after login")
    print("="*60 + "\n")
    
    try:
        # Wait for the chat input to appear (indicates successful login)
        await page.wait_for_selector(
            'textarea[id="prompt-textarea"], div[id="prompt-textarea"]',
            timeout=timeout * 1000
        )
        logger.info("Login successful - chat input detected")
        return True
    except Exception as e:
        logger.error(f"Login timeout: {e}")
        return False


async def upload_images(page, image_paths: List[str]) -> bool:
    """
    Upload multiple images to ChatGPT.
    """
    if not image_paths:
        return True
    
    logger.info(f"Uploading {len(image_paths)} images...")
    
    try:
        # Find the file input element
        # ChatGPT uses a hidden file input for uploads
        file_input = await page.query_selector('input[type="file"]')
        
        if not file_input:
            # Try to click the attachment button first to reveal the input
            attach_button = await page.query_selector('button[aria-label*="Attach"], button[data-testid="attach-button"]')
            if attach_button:
                await attach_button.click()
                await asyncio.sleep(0.5)
                file_input = await page.query_selector('input[type="file"]')
        
        if not file_input:
            logger.error("Could not find file input element")
            return False
        
        # Upload all files at once
        await file_input.set_input_files(image_paths)
        
        # Wait for uploads to complete (images should appear in the chat)
        await asyncio.sleep(2 + len(image_paths) * 0.5)  # Scale wait time with image count
        
        logger.info(f"Successfully uploaded {len(image_paths)} images")
        return True
        
    except Exception as e:
        logger.error(f"Failed to upload images: {e}")
        return False


async def submit_prompt(page, prompt_text: str) -> bool:
    """
    Type and submit a prompt to ChatGPT.
    """
    logger.info("Submitting prompt...")
    
    try:
        # Find the textarea
        textarea = await page.query_selector('textarea[id="prompt-textarea"], div[id="prompt-textarea"]')
        
        if not textarea:
            logger.error("Could not find prompt textarea")
            return False
        
        # Clear any existing text and type the prompt
        await textarea.click()
        await textarea.fill(prompt_text)
        
        await asyncio.sleep(0.5)
        
        # Find and click the send button
        send_button = await page.query_selector('button[data-testid="send-button"], button[aria-label="Send prompt"]')
        
        if send_button:
            await send_button.click()
        else:
            # Try pressing Enter as fallback
            await textarea.press("Enter")
        
        logger.info("Prompt submitted")
        return True
        
    except Exception as e:
        logger.error(f"Failed to submit prompt: {e}")
        return False


async def wait_for_response(page, timeout: int = 300) -> Optional[str]:
    """
    Wait for ChatGPT to finish generating a response.
    Returns the response text or None on timeout.
    """
    logger.info(f"Waiting for response (timeout: {timeout}s)...")
    
    start_time = asyncio.get_event_loop().time()
    last_response = ""
    stable_count = 0
    
    while asyncio.get_event_loop().time() - start_time < timeout:
        try:
            # Check if still generating (stop button visible)
            stop_button = await page.query_selector('button[aria-label="Stop generating"]')
            
            # Get the latest assistant response
            responses = await page.query_selector_all('div[data-message-author-role="assistant"]')
            
            if responses:
                latest_response = await responses[-1].inner_text()
                
                # Check if response is stable (not changing)
                if latest_response == last_response and len(latest_response) > 50:
                    stable_count += 1
                    if stable_count >= 3 and not stop_button:
                        logger.info("Response complete")
                        return latest_response
                else:
                    stable_count = 0
                    last_response = latest_response
            
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.warning(f"Error checking response: {e}")
            await asyncio.sleep(2)
    
    logger.warning("Response timeout - returning partial response")
    return last_response if last_response else None


def extract_json_from_response(response_text: str) -> Optional[dict]:
    """
    Extract JSON from ChatGPT response text.
    Handles JSON in code blocks or raw JSON.
    """
    import re
    
    if not response_text:
        return None
    
    # Try to find JSON in code blocks first
    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    matches = re.findall(code_block_pattern, response_text)
    
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    
    # Try to find raw JSON (starts with { and ends with })
    start = response_text.find('{')
    if start != -1:
        depth = 0
        for i, char in enumerate(response_text[start:], start):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(response_text[start:i+1])
                    except json.JSONDecodeError:
                        break
    
    return None


async def analyze_with_chatgpt(
    prompt_text: str,
    screenshot_paths: List[str],
    headless: bool = False,
    timeout: int = 300
) -> Tuple[bool, Optional[dict], Optional[str]]:
    """
    Full automation flow: login, upload images, submit prompt, get response.
    
    Args:
        prompt_text: The analysis prompt to submit
        screenshot_paths: List of paths to screenshot images
        headless: Run browser in headless mode (False recommended for first run)
        timeout: Max time to wait for response in seconds
        
    Returns:
        Tuple of (success, parsed_json, raw_response)
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return False, None, None
    
    logger.info("Starting ChatGPT automation...")
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # Create context with saved cookies if available
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Load saved cookies
        saved_cookies = load_cookies()
        if saved_cookies:
            await context.add_cookies(saved_cookies)
        
        page = await context.new_page()
        
        try:
            # Navigate to ChatGPT
            logger.info("Navigating to ChatGPT...")
            await page.goto(CHATGPT_NEW_CHAT_URL, wait_until="networkidle", timeout=60000)
            
            await asyncio.sleep(2)
            
            # Check if we need to login
            chat_input = await page.query_selector('textarea[id="prompt-textarea"], div[id="prompt-textarea"]')
            
            if not chat_input:
                # Need to login
                logger.info("Login required...")
                if not await wait_for_login(page):
                    logger.error("Login failed or timed out")
                    return False, None, "Login failed"
                
                # Save cookies after successful login
                cookies = await context.cookies()
                save_cookies(cookies)
            
            await asyncio.sleep(1)
            
            # Upload screenshots
            if screenshot_paths:
                if not await upload_images(page, screenshot_paths):
                    logger.warning("Image upload failed, continuing without images")
            
            await asyncio.sleep(1)
            
            # Submit the prompt
            if not await submit_prompt(page, prompt_text):
                return False, None, "Failed to submit prompt"
            
            # Wait for response
            raw_response = await wait_for_response(page, timeout)
            
            if not raw_response:
                return False, None, "No response received"
            
            # Save cookies again (session might have been refreshed)
            cookies = await context.cookies()
            save_cookies(cookies)
            
            # Extract JSON from response
            parsed_json = extract_json_from_response(raw_response)
            
            if parsed_json:
                logger.info("Successfully extracted JSON from response")
                return True, parsed_json, raw_response
            else:
                logger.warning("Could not parse JSON from response")
                return True, None, raw_response
                
        except Exception as e:
            logger.error(f"Automation error: {e}")
            return False, None, str(e)
            
        finally:
            await browser.close()


async def test_chatgpt_connection(headless: bool = False) -> bool:
    """
    Test if we can connect to ChatGPT with saved session.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        
        saved_cookies = load_cookies()
        if saved_cookies:
            await context.add_cookies(saved_cookies)
        
        page = await context.new_page()
        
        try:
            await page.goto(CHATGPT_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # Check if logged in
            chat_input = await page.query_selector('textarea[id="prompt-textarea"], div[id="prompt-textarea"]')
            
            await browser.close()
            return chat_input is not None
            
        except Exception:
            await browser.close()
            return False


# CLI helper for testing
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        # Test connection
        print("Testing ChatGPT connection...")
        connected = await test_chatgpt_connection(headless=False)
        print(f"Connected: {connected}")
        
        if not connected:
            print("\nConnection failed. The browser will open for login.")
            success, data, raw = await analyze_with_chatgpt(
                prompt_text="Hello! Please respond with a simple JSON: {\"status\": \"ok\"}",
                screenshot_paths=[],
                headless=False,
                timeout=60
            )
            print(f"Success: {success}")
            print(f"Data: {data}")
    
    asyncio.run(main())
