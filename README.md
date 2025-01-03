# Web Crawler

A robust, asynchronous web crawler designed to extract product URLs from e-commerce websites. The crawler supports parallel processing of multiple domains while handling dynamic content and implementing various optimization strategies.

## Features

- Parallel crawling of multiple domains
- Dynamic content handling via Selenium
- Configurable depth and URL limits
- Automatic handling of JavaScript-loaded content
- Custom URL pattern matching for products
- Domain-specific exclusion patterns
- Comprehensive logging system
- Rate limiting and timeout controls

## Requirements

```
python >= 3.7
aiohttp
beautifulsoup4
selenium
```

## Installation

1. Clone the repository
2. Create virtual environment:
  ```sh
  python3 -m venv venv 
  ```
3. Activate the environemtn:
```sh
  C:> venv\Scripts\activate.bat # For Windows
  source venv/bin/activate # For Linux/MacOS 
```
4. Install dependencies:
  ```bash
  pip install aiohttp beautifulsoup4 selenium
  ```
5. Start the program
```bash
python3 version2.py
```

## Usage

Basic usage example:

```python
domains = [
    "https://flipkart.com",
    "https://amazon.in"
]

crawler = ParallelCrawler(
    domains=domains,
    max_urls_per_domain=500,
    max_depth=3,
    timeout_seconds=3600
)
crawler.run()
```

## Configuration

- `domains`: List of domains to be crawled
- `max_urls_per_domain`: Maximum number of URLs to crawl per domain (default: 10000)
- `max_depth`: Maximum depth for crawling links (default: 10)
- `timeout_seconds`: Timeout for crawling operation per domain (default: 3600)
- `output_file`: Path for JSON output file (default: 'product_urls.json')



## Output

Results are saved in JSON format:
```json
{
  "flipkart.com": [
    "https://flipkart.com/product/1",
    "https://domaflipkartin1.com/product/2"
  ],
  "amazon.com": [
    "https://amazon.com/product/1"
  ]
}
```

## Logging

The crawler logs all operations to both console and 'crawler.log' file, including:
- Crawling progress
- Error messages
- CAPTCHA detection
- Timeout warnings

## Execution flow

1. **ParallelCrawler** class object is intialised
2. `ParallelCrawler.run()` method is called which in turn calls the async function `ParallelCrawler.crawl_all_domains()` with asyncio to execute asyncronous functions
3. **DomainCrawler object** `(crawler)` is intialised over all the domains and start executing parallely. i.e. in simple words - A bot is set-up on every domain and start scraping the domains independently & parallely.
4. `DomainCrawler.start()` : Starts the crawling of a domain
5. `DomainCrawler.crawl_url()` : Extracts all the urls on a page. It checks if the url *is product page* by matching certain product page URL patterns.
    - If **YES** -  Adds it to product URLs list
    - If **NO** - Checks if it's within depth limit and not excluded, then crawls it to find more product URLs
6. `DomainCrawler.handle_dynamic_content()`: If a page uses JavaScript to load content:
    - Opens the page in a headless browser
    - Scrolls to load all content
    - Extracts URLs from the fully loaded page
7. The process continues until:
    - Maximum URLs limit is reached
    - Maximum depth is reached
    - Timeout occurs
    - User stops the program
8. Finally, all collected product URLs are saved to a JSON file, organized by domain