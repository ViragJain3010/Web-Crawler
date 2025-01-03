# main.py
import asyncio
import json
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
import re
from typing import List, Dict, Set
from playwright_stealth import stealth_async
import random


class EcommerceCrawler:
    def __init__(self, domains: List[str]):
        self.domains = domains
        self.product_urls: Dict[str, Set[str]] = {domain: set() for domain in domains}
        # Common product URL patterns
        self.product_patterns = [
            r'/product/',
            r'/p/',
            r'/item/',
            r'/pd/',
            r'/dp/',
            r'/-i-',  # common in some e-commerce sites
        ]

    async def random_delay(min_delay=2, max_delay=5):
        await asyncio.sleep(random.uniform(min_delay, max_delay))

    def is_product_url(self, url: str) -> bool:
        """Check if a URL is likely a product page based on common patterns."""
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in self.product_patterns)

    def is_same_domain(self, url: str, domain: str) -> bool:
        """Check if URL belongs to the same domain."""
        parsed_url = urlparse(url)
        return domain in parsed_url.netloc

    async def crawl_page(self, page, domain: str, visited_urls: Set[str]):
        """Crawl a single page and extract product URLs."""
        try:
            # Get all links on the page
            links = await page.evaluate('''
                () => Array.from(document.querySelectorAll('a'))
                    .map(a => a.href)
                    .filter(href => href.startsWith('http'))
            ''')

            for url in links:
                if url in visited_urls or not self.is_same_domain(url, domain):
                    continue

                visited_urls.add(url)
                if self.is_product_url(url):
                    self.product_urls[domain].add(url)

            return links

        except Exception as e:
            print(f"Error crawling {page.url}: {str(e)}")
            return []

    async def crawl_domain(self, domain: str):
        """Crawl a single domain for product URLs."""
        visited_urls = set()
        urls_to_visit = {f"https://{domain}"}

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)  # Headless mode off
            context = await browser.new_context()
            await stealth_async(context)  # Apply stealth
            page = await context.new_page()

            while urls_to_visit and len(visited_urls) < 100:  # Limit for testing
                url = urls_to_visit.pop()
                if url in visited_urls:
                    continue

                try:
                    print(f"Visiting: {url}")
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    await self.random_delay()
                    new_urls = await self.crawl_page(page, domain, visited_urls)
                    urls_to_visit.update(
                        url for url in new_urls 
                        if url not in visited_urls 
                        and self.is_same_domain(url, domain)
                    )

                except Exception as e:
                    print(f"Error accessing {url}: {str(e)}")

            await browser.close()


    async def crawl_all_domains(self):
        """Crawl all domains concurrently."""
        tasks = [self.crawl_domain(domain) for domain in self.domains]
        await asyncio.gather(*tasks)

    def save_results(self, filename: str = "product_urls.json"):
        """Save discovered URLs to a JSON file."""
        # Convert sets to lists for JSON serialization
        results = {domain: list(urls) for domain, urls in self.product_urls.items()}
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)

# Example usage
if __name__ == "__main__":
    domains = [
        "amazon.com",
        "flipkart.com"
    ]
    
    crawler = EcommerceCrawler(domains)
    asyncio.run(crawler.crawl_all_domains())
    crawler.save_results()