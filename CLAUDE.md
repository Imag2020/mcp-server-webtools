# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an MCP (Model Context Protocol) server that provides web automation tools using FastAPI, FastMCP, and Playwright. The server exposes web browsing capabilities as MCP tools for AI assistants.

## Running the Server

```bash
python mcp-wetools.py
```

The server runs on `http://0.0.0.0:8000` and provides:
- SSE endpoint at `/sse` for real-time communication
- Message endpoint at `/messages` for MCP protocol

## Architecture

**Single-file architecture**: The entire MCP server is contained in `mcp-wetools.py`

**Core Components**:
- **Browser Management**: Global Playwright browser instance with lifecycle management
- **FastMCP Integration**: Uses FastMCP framework to expose Python functions as MCP tools
- **Web Automation Tools**: Set of tools for navigation, content extraction, form filling, and interaction

**Key Global Variables**:
- `playwright`, `browser`, `page`: Playwright browser state
- `work_dir`: Working directory for file operations

## Available MCP Tools

The server exposes these tools to MCP clients:

### Navigation & Content
- `navigate_to(url)`: Navigate to a URL
- `get_content()`: Extract readable text from current page in markdown format
- `save_pdf(output_path)`: Save current page as PDF
- `print_screen(output_path)`: Take screenshot of current page

### Form Interaction
- `fill_form_field(label, value)`: Fill form fields by label text
- `submit_form_auto(fields, submit_button_text)`: Fill multiple fields and submit form
- `click(text, selector, exact_match, return_content)`: Click elements by text or CSS selector

### Popup Management
- `check_popups()`: Detect visible popups/dialogs
- `close_popups()`: Close common popup types (cookies, consent, etc.)
- `force_close_google_popup()`: Specifically handle Google popups

### System
- `shutdown()`: Clean shutdown of browser and server

## Browser Lifecycle

- Browser launches headless on server startup
- Single persistent browser/page instance shared across all tool calls
- Automatic cleanup on server shutdown
- Page state persists between tool calls

## Error Handling

All tools return structured responses with:
- `status`: "success", "error", or "partial_success"
- `message`: Error details when applicable
- Tool-specific data on success

## Text Extraction

The `extract_readable_text()` function converts HTML to markdown format, extracting:
- Headers (h1-h6) with proper markdown formatting
- Paragraphs, lists, and links
- Filtered and cleaned text content