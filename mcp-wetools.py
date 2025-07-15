from fastapi import FastAPI
from fastmcp import FastMCP
from fastmcp.server.http import create_sse_app
from playwright.async_api import async_playwright
from contextlib import asynccontextmanager
import logging
import asyncio
import json
import re
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

playwright = None
browser = None
page = None
work_dir=""

# Initialise le navigateur
async def init_browser():
    global playwright, browser, page
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page()
    logger.info("Browser initialized")

# Ferme proprement le navigateur
async def cleanup_browser():
    global playwright, browser, page
    if page:
        await page.close()
    if browser:
        await browser.close()
    if playwright:
        await playwright.stop()
    logger.info("Browser cleanup done")

# Formater le texte 
async def extract_readable_text(page):
    elements = await page.query_selector_all("h1, h2, h3, h4, h5, h6, p, li, a, span, div")
    markdown = []
    for element in elements:
        tag = await element.evaluate("el => el.tagName.toLowerCase()")
        text = await element.text_content()
        if text:
            text = re.sub(r'\s+', ' ', text.strip())
            if not text:
                continue
            if tag in ["h1","h2","h3","h4","h5","h6"]:
                level = int(tag[1])
                markdown.append(f"{'#'*level} {text}")
            elif tag == "p":
                markdown.append(f"{text}\n")
            elif tag == "li":
                markdown.append(f"- {text}")
            elif tag == "a":
                href = await element.get_attribute("href") or ""
                markdown.append(f"[{text}]({href})")
            else:
                markdown.append(f"{text}\n")
    return "\n".join(line for line in markdown if line.strip())



# Crée l'instance FastMCP
mcp = FastMCP()

# Déclare les tools


@mcp.tool(description="Navigato to url")
async def navigate_to(url: str) -> Dict[str, Any]:
    try:
        await page.goto(url, wait_until='networkidle')
        return {"status":"success", "url": url}
    except Exception as e:
        logger.error(f"navigate_to error: {e}")
        return {"status":"error", "message": str(e)}


@mcp.tool(description="Get readable text of current page content")
async def get_content() -> Dict[str, Any]:
    try:
        content = await extract_readable_text(page)
        return {"status":"success", "current_url": page.url, "page_title": await page.title(), "content": content}
    except Exception as e:
        logger.error(f"get_content error: {e}")
        return {"status":"error", "message": str(e)}

@mcp.tool(description="Print current page as a pdf file")
async def save_pdf(output_path: str = "output.pdf"):
    global work_dir
    try:
        await page.pdf(path=work_dir+output_path)
        return {"saved": True, "path": work_dir+output_path}
    except Exception as e:
        logger.error(f"save_pdf error: {e}")
        return {"status":"error", "message": str(e)}    


@mcp.tool(description="Print current page screen to a png file")
async def print_screen(output_path: str = "screenshot.png"):
    global work_dir
    try:
        await page.screenshot(path=work_dir+output_path, full_page=True)
        return {"screenshot": work_dir+output_path}
    
    except Exception as e:
        logger.error(f"print_screen error: {e}")
        return {"status":"error", "message": str(e)}


@mcp.tool(description="Fill input, text area fields")
async def fill_form_field(label: str, value: str) -> Dict[str, Any]:
    label_text = label.strip().lower()
    for frame in page.frames:
        try:
            labels = await frame.query_selector_all("label")
            for label_el in labels:
                try:
                    text = (await label_el.text_content() or "").strip().lower()
                    if label_text in text:
                        target_id = await label_el.get_attribute("for")
                        if target_id:
                            input_el = await frame.query_selector(f"#{target_id}")
                            if input_el:
                                await input_el.fill(value)
                                return {"status":"success","method":"for-id","label":text,"frame":frame.url,"filled_value":value}
                        else:
                            input_el = await label_el.query_selector("input, textarea, select")
                            if input_el:
                                await input_el.fill(value)
                                return {"status":"success","method":"nested-in-label","label":text,"frame":frame.url,"filled_value":value}
                        parent = await label_el.evaluate_handle("el => el.parentElement")
                        if parent:
                            input_el = await parent.query_selector("input, textarea, select")
                            if input_el:
                                await input_el.fill(value)
                                return {"status":"success","method":"sibling-of-label","label":text,"frame":frame.url,"filled_value":value}
                except:
                    continue
        except:
            continue
    return {"status":"error", "message": f"Champ associé au label '{label}' non trouvé"}

@mcp.tool(description="Fill input, text area flields and submit form")
async def submit_form_auto(fields: str, submit_button_text: str = "Envoyer") -> Dict[str, Any]:
    try:
        fields_dict = json.loads(fields) if isinstance(fields, str) else fields
    except Exception:
        return {"status":"error", "message":"Invalid JSON format for fields"}

    results = []
    for label, val in fields_dict.items():
        res = await fill_form_field(label, val)
        results.append(res)

    submit_keywords = [submit_button_text.lower(), "envoyer", "submit", "valider", "confirmer"]
    for frame in page.frames:
        try:
            buttons = await frame.query_selector_all("button, input[type='submit']")
            for btn in buttons:
                text = await btn.text_content() or ""
                if any(k in text.lower() for k in submit_keywords):
                    if await btn.is_visible():
                        await btn.click()
                        await page.wait_for_timeout(1500)
                        return {"status":"success","submitted":True,"fields_filled":results,"button_text":text.strip(),"frame_url":frame.url}
        except:
            continue
    return {"status":"partial_success","submitted":False,"fields_filled":results,"message":"No submit button found"}

@mcp.tool(description="Click a button by its selector or text content")
async def click(text: str = "", selector: str = "", exact_match: bool = False, return_content: bool = False) -> Dict[str, Any]:
    if not text and not selector:
        return {"status":"error", "message":"Either 'text' or 'selector' is required"}

    try:
        element = None
        strategy_used = None

        if selector:
            element = await page.query_selector(selector)
            if element:
                visible = await element.is_visible()
                enabled = await element.is_enabled()
                if visible and enabled:
                    strategy_used = f"CSS selector: {selector}"
                else:
                    element = None
        elif text:
            strategies = [
                f"text='{text}'" if exact_match else f"text={text}",
                f"[aria-label*='{text}' i]",
                f"[title*='{text}' i]",
                f"[alt*='{text}' i]",
                f"button:has-text('{text}')",
                f"a:has-text('{text}')",
                f"input[value*='{text}' i]",
                f"*:has-text('{text}'):not(html):not(body)"
            ]
            for strat in strategies:
                try:
                    element = await page.query_selector(strat)
                    if element:
                        visible = await element.is_visible()
                        enabled = await element.is_enabled()
                        if visible and enabled:
                            strategy_used = strat
                            break
                        else:
                            element = None
                except:
                    continue

        if not element:
            return {"status":"error", "message": f"No clickable element found for '{text or selector}'"}

        await element.scroll_into_view_if_needed()
        await page.wait_for_timeout(500)
        url_before = page.url
        try:
            await element.click()
        except:
            await element.click(force=True)
        await page.wait_for_timeout(2000)
        url_after = page.url
        url_changed = url_before != url_after

        response = {
            "status": "success",
            "clicked_element": text or selector,
            "strategy_used": strategy_used,
            "url_before": url_before,
            "current_url": url_after,
            "url_changed": url_changed,
            "page_title": await page.title()
        }
        if url_changed or return_content:
            content = await extract_readable_text(page)
            response["new_content"] = content

        return response

    except Exception as e:
        logger.error(f"click error: {e}")
        return {"status":"error", "message": str(e)}


@mcp.tool(description="Check if any popups in current page")
async def check_popups() -> Dict[str, Any]:
    try:
        popups = []
        selectors = [
            "div[role='dialog']", "div[aria-modal='true']", "text=Tout accepter",
            "text=Tout refuser", "text=Accepter tout", "text=Refuser tout",
            "text=Accept all", "text=Reject all", ".cookie-banner",
            ".consent-banner", "#cookie-consent", "[data-testid*='cookie']", "[data-testid*='consent']"
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    txt = await el.text_content()
                    popups.append({"selector": sel, "text": (txt[:100] if txt else ""), "visible": True})
            except:
                continue
        return {"status":"success", "popups_found": popups, "popup_count": len(popups), "current_url": page.url}
    except Exception as e:
        logger.error(f"check_popups error: {e}")
        return {"status":"error", "message": str(e)}

@mcp.tool(description="Close pupups")
async def close_popups() -> Dict[str, Any]:
    try:
        closed = []
        selectors = [
            "text=Tout refuser", "text=Refuser tout", "text=Reject all", "text=Decline all",
            "text=Non merci", "text=No thanks", "button[aria-label*='close' i]",
            "button[aria-label*='fermer' i]", "button[title*='close' i]", "button[title*='fermer' i]",
            ".close-button", ".btn-close", "[data-testid*='close']", "[data-testid*='reject']", "[data-testid*='decline']"
        ]
        for sel in selectors:
            for frame in page.frames:
                try:
                    btn = await frame.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        closed.append(sel)
                        await page.wait_for_timeout(1000)
                        break
                except:
                    continue
            if closed:
                break
        return {"status":"success", "closed_popups": closed}
    except Exception as e:
        logger.error(f"close_popups error: {e}")
        return {"status":"error", "message": str(e)}

@mcp.tool(description="Close google pupups")
async def force_close_google_popup() -> Dict[str, Any]:
    keywords = ["refuser", "reject", "no thanks", "non merci", "decline"]
    buttons = await page.query_selector_all("button")
    for btn in buttons:
        txt = (await btn.text_content() or "").lower()
        if any(k in txt for k in keywords) and await btn.is_visible():
            await btn.click()
            await page.wait_for_timeout(1000)
            return {"status":"success", "clicked_text": txt}
    return {"status":"not_found"}



@mcp.tool()
async def shutdown():
    await cleanup_browser()
    asyncio.create_task(stop_server())
    return {"shutdown": True}

async def stop_server():
    await asyncio.sleep(1)
    import os
    os._exit(0)

# FastAPI app
app = FastAPI()

# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_browser()
    yield
    await cleanup_browser()

app.router.lifespan_context = lifespan

# Montre l'app SSE sur les bons endpoints
sse_app = create_sse_app(mcp, message_path="/messages", sse_path="/sse")
app.mount("/", sse_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

