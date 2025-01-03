# E-commerce Product URL Crawler

This project is an advanced **web crawler** designed to discover product URLs from multiple e-commerce websites. It uses **Playwright** for browser automation and includes features like dynamic content handling, infinite scroll simulation, and robust URL matching heuristics.

---

## Features

- **Domain-based Crawling**: Targets specific e-commerce domains.
- **Dynamic Content Support**: Handles dynamically loaded content and infinite scrolling.
- **Product Page Detection**:
  - URL pattern matching.
  - Content pattern heuristics (e.g., "Add to Cart", "Product Description").
  - Schema.org structured data parsing for `"@type": "Product"`.
- **Retry Mechanism**: Handles intermittent network or server errors.
- **Stealth Mode**: Avoids bot detection using `playwright_stealth`.
- **JSON Output**: Stores discovered URLs in a structured file.

---

## Requirements

### Prerequisites

- **Python 3.9+**
- **Node.js** (required for Playwright installation)
- **Playwright** and its browser dependencies

### Python Dependencies

Install dependencies using `pip`:

```bash
pip install -r requirements.txt
```

Example `requirements.txt`:
```
asyncio
playwright
playwright-stealth
```

---

## Usage

### 1. Clone the Repository

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Target Domains

Update the `domains` list in the `main` block:

```python
domains = [
    "amazon.com",
    "flipkart.com"
]
```

### 4. Run the Crawler

Run the program with:

```bash
python advance.py
```

The crawler will:
- Navigate to each domain.
- Extract product URLs.
- Handle dynamic content and infinite scroll.
- Save the results to a JSON file.

---

## Output

Discovered URLs are saved in `product_urls.json`. Example structure:

```json
{
  "amazon.com": {
    "urls": [
      "https://www.amazon.com/product/1234",
      "https://www.amazon.com/dp/B09XYZ"
    ],
    "count": 2,
    "timestamp": "2025-01-01T12:00:00Z"
  },
  "flipkart.com": {
    "urls": [
      "https://www.flipkart.com/item/4567"
    ],
    "count": 1,
    "timestamp": "2025-01-01T12:00:00Z"
  }
}
```

---

## Key Components

### 1. Initialization
- **Domains**: List of e-commerce websites to crawl.
- **Configurations**: Includes retry logic, scrolling behavior, and dynamic content handling.

### 2. Crawling Workflow
- **`crawl_all_domains`**: Handles multiple domains concurrently.
- **`crawl_domain`**: Navigates through each domain's pages and extracts URLs.
- **`crawl_page`**: Processes individual pages, detecting product pages and handling dynamic content.

### 3. URL Matching
- **`is_product_page`**:
  - Matches URL patterns like `/product/1234`.
  - Detects content patterns like "Add to Cart".
  - Parses `Schema.org` data for product identification.

### 4. Infinite Scroll Handling
- Simulates user scrolling.
- Detects and clicks "Load More" buttons if present.

### 5. Retry Logic
- Retries failed requests up to a configurable maximum.

---

## Configuration Options

You can customize various crawler parameters in the `EcommerceCrawler` constructor:

```python
crawler = EcommerceCrawler(
    domains=["amazon.com", "flipkart.com"],
    max_retries=3,              # Retry count for failed requests
    retry_delay=5,              # Delay between retries (seconds)
    scroll_timeout=30,          # Max time for infinite scrolling (seconds)
    max_scroll_attempts=10,     # Max scrolling attempts per page
    dynamic_wait=5              # Wait time for dynamic content (seconds)
)
```

---

## Example

1. Start with domains:
   ```python
   domains = ["amazon.com"]
   ```
2. The crawler extracts URLs like:
   - `https://www.amazon.com/product/1234`
   - `https://www.amazon.com/dp/B09XYZ`
3. Saves results in `product_urls.json`.

---

## Logging

Logs are written to `crawler.log` and displayed in the console. Example log:

```
2025-01-01 12:00:00 - INFO - Found product URL: https://www.amazon.com/product/1234 (confidence: 0.95)
2025-01-01 12:05:00 - ERROR - Failed to access https://www.amazon.com after 3 attempts.
```

---

## Troubleshooting

- **Error: Playwright not installed**:
  Run:
  ```bash
  pip install playwright
  playwright install
  ```

- **Slow Crawling**:
  - Reduce `dynamic_wait` or increase `scroll_timeout`.

- **Bot Detection**:
  - Ensure `stealth_async` is properly applied.
