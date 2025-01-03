# main.py
import asyncio
import json
import logging
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright, TimeoutError
import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from playwright_stealth import stealth_async

# Todo: Move handle_dynamic_content, should_crawl_url, extract_urls_from_page, is_same_domain, save_results to utils

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log'),
        logging.StreamHandler()
    ]
)

@dataclass
class ProductUrlMatch:
    url: str
    confidence: float
    matched_patterns: List[str]

class EcommerceCrawler:
    def __init__(self, 
                 domains: List[str], 
                 amazon_credentials: Optional[Dict[str, str]] = None,
                 max_retries: int = 3, 
                 retry_delay: int = 5,
                 scroll_timeout: int = 30,
                 max_scroll_attempts: int = 10,
                 dynamic_wait: int = 5): # Time to wait for dynamic content (seconds)
        self.domains = domains
        self.product_urls: Dict[str, Set[str]] = {domain: set() for domain in domains}
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.scroll_timeout = scroll_timeout
        self.max_scroll_attempts = max_scroll_attempts
        self.dynamic_wait = dynamic_wait
        self.amazon_credentials = amazon_credentials
        
        # Enhanced product URL patterns with confidence scores
        self.url_patterns = [
            # High confidence patterns (0.9+)
            (r'/product[s]?/[\w-]+', 0.95),
            (r'/p/[\w-]+', 0.95),
            (r'/dp/', 0.95),
            (r'/item/[\w-]+', 0.95),
            (r'/-i-[\w-]+', 0.95),
            
            # Medium confidence patterns (0.7-0.9)
            (r'/pd/[\w-]+', 0.8),
            (r'/[\w-]+-p-[\d]+', 0.8),
            
            # Lower confidence patterns (0.5-0.7)
            (r'/shop/[\w-]+', 0.6),
            (r'/[\w-]+-[\d]+\.html', 0.6)
        ]

        # HTML content patterns that indicate a product page
        self.content_patterns = [
            (r'Add to (?:Cart|Basket)', 0.8),
            (r'Product Description', 0.7),
            (r'Buy Now', 0.7),
            (r'Add to Wishlist', 0.6),
            (r'Specifications', 0.6),
            (r'Technical Details', 0.6),
            (r'Price', 0.5),
            (r'SKU|Item Code', 0.5)
        ]

        # Add patterns for detecting load more buttons and infinite scroll containers
        self.load_more_patterns = [
            'load more', 'show more', 'view more', 'load products',
            'next page', 'more items', 'more products'
        ]

        # Add excluded paths
        self.excluded_paths = [
            '/stories',
            '/payments',
            '/about-us',
            '/contact-us',
            '/help',
            '/footer',
            '/policy',
            '/terms',
            '/careers',
            '/blog'
        ]

        self.amazon_content_patterns = [
            (r'#productTitle', 0.9),
            (r'#priceblock_ourprice', 0.8),
            (r'#buy-now-button', 0.8),
            (r'#add-to-cart-button', 0.8),
            (r'#breadcrumb-back-link', 0.7),
        ]

        self.amazon_product_patterns = [
            (r'/dp/[A-Z0-9]{10}', 0.95),
            (r'/gp/product/[A-Z0-9]{10}', 0.95),
            (r'/[A-Za-z0-9-]+/dp/[A-Z0-9]{10}', 0.95),
        ]


    async def crawl_all_domains(self):
        """Crawl all domains concurrently.

        Parallel execution of all domains acheived by `asyncio.gather()` adding them in the tasks array and  crawling over them.
        """
        try:
            tasks = [self.crawl_domain(domain) for domain in self.domains]
            await asyncio.gather(*tasks)
        except Exception as e:
            logging.error(f"Error in crawl_all_domains: {str(e)}")

    async def crawl_domain(self, domain: str):
        """Enhanced crawl_domain method with Amazon-specific handling."""
        visited_urls = set()
        homepage_url = f"https://www.{domain}"

        start_time = datetime.now()

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            await stealth_async(context)
            
            context.set_default_timeout(30000)
            context.set_default_navigation_timeout(30000)
            
            page = await context.new_page()
            
            try:
                # Step 1: Visit homepage
                logging.info(f"Visiting homepage: {homepage_url}")
                if not await self.crawl_with_retry(page, homepage_url):
                    logging.error("Failed to load homepage")
                    return

                # Step 2: Handle CAPTCHA if present
                # if not await self.handle_amazon_captcha(page):
                #     logging.error("Failed to handle CAPTCHA")
                #     return
                # Handle Amazon-specific authentication if needed
                # if domain == "amazon.com":
                #     initial_url = urls_to_visit.pop()
                #     if await self.crawl_with_retry(page, initial_url):
                #         if not await self.handle_amazon_auth(page):
                #             logging.error("Failed to handle Amazon authentication")
                #             return
                #         urls_to_visit.add(initial_url)

                # Step 3: Collect all hrefs from homepage
                homepage_urls = await self.extract_urls_from_page(page)
                logging.info(f"Found {len(homepage_urls)} URLs on homepage")

                # Step 4: Crawl collected URLs and check for product pages
                urls_to_visit = homepage_urls - visited_urls
                visited_urls.add(homepage_url)

                # Continue with normal crawling
                while urls_to_visit and len(visited_urls) < 50:  # for testing purposes
                    url = urls_to_visit.pop()
                    if url in visited_urls:
                        continue

                    visited_urls.add(url)
                    if await self.crawl_with_retry(page, url):
                        new_urls = await self.crawl_page(page, domain, visited_urls)
                        urls_to_visit.update(
                            url for url in new_urls 
                            if url not in visited_urls 
                            and url not in urls_to_visit
                            and self.should_crawl_url(url, domain)
                        )

            except Exception as e:
                logging.error(f"Error crawling domain {domain}: {str(e)}")
            finally:
                await browser.close()

        duration = datetime.now() - start_time
        logging.info(f"Finished crawling {domain}. Duration: {duration}. "
                    f"Found {len(self.product_urls[domain])} product URLs.")

    # async def crawl_with_retry(self, page, url: str, retry_count: int = 0):
    #     """Attempt to crawl a page with retry mechanism."""
    #     try:
    #         # First wait for navigation
    #         await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
    #         # Then wait for either network idle or a reasonable timeout
    #         try:
    #             await page.wait_for_load_state("networkidle", timeout=30000)
    #         except TimeoutError:
    #             logging.info(f"Network didn't reach idle state for {url}, but continuing anyway")
            
    #         return True
    #     except Exception as e:
    #         if retry_count < self.max_retries:
    #             logging.warning(f"Error accessing {url}, attempt {retry_count + 1}/{self.max_retries}: {str(e)}")
    #             await asyncio.sleep(self.retry_delay * (retry_count + 1))  # Exponential backoff
    #             return await self.crawl_with_retry(page, url, retry_count + 1)
    #         else:
    #             logging.error(f"Failed to access {url} after {self.max_retries} attempts: {str(e)}")
    #             return False

    async def crawl_with_retry(self, page, url: str, retry_count: int = 0):
        """Enhanced crawl_with_retry with quick product page check."""
        try:
            # First check if it's an Amazon product URL using regex
            if 'amazon' in url:
                for pattern, confidence in self.amazon_product_patterns:
                    if re.search(pattern, url):
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        # If it's a product URL, we don't need to wait for everything to load
                        self.product_urls[urlparse(url).netloc].add(url)
                        logging.info(f"Found product URL (from pattern): {url}")
                        return True

            # If not a direct product URL, proceed with normal loading
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Quick CAPTCHA check before proceeding
            if await self.is_captcha_present(page):
                if not await self.handle_amazon_captcha(page):
                    return False

            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except TimeoutError:
                logging.info(f"Network didn't reach idle state for {url}, but continuing anyway")
            
            return True

        except Exception as e:
            if retry_count < self.max_retries:
                logging.warning(f"Error accessing {url}, attempt {retry_count + 1}/{self.max_retries}: {str(e)}")
                await asyncio.sleep(self.retry_delay * (retry_count + 1))
                return await self.crawl_with_retry(page, url, retry_count + 1)
            else:
                logging.error(f"Failed to access {url} after {self.max_retries} attempts: {str(e)}")
                return False
            
    def should_crawl_url(self, url: str, domain: str) -> bool:
        """Determine if URL should be crawled based on rules."""
        try:
            parsed_url = urlparse(url)
            
            # Check if URL is from the same domain
            if domain not in parsed_url.netloc:
                return False
            
            # Amazon-specific exclusions
            amazon_excluded_patterns = [
            '/minitv',
            'advertising.amazon',
            'brandservices.amazon',
            'accelerator.amazon',
            'aboutamazon',
            '/s/',  # search pages
            '/b/',  # browse pages
            '/hz/wishlist',
            '/hz/',
            '/gp/help',
            '/gp/css',
            '/ap/signin',
            '/ap/',
            '/gp/cart',
            '/gp/registry',
            '/stores/',
            '/music/',
            '/prime',
            '/deals',
            '/gift-cards',
            '/gcx/',
            '/services',
            '/business',
            '/musical-instruments'
            ]

            # Check Amazon-specific exclusions
            url_lower = url.lower()
            if any(pattern in url_lower for pattern in amazon_excluded_patterns):
                return False
                
            # Check against excluded paths
            path = parsed_url.path.lower()
            if any(excluded in path for excluded in self.excluded_paths):
                return False
                
            # Avoid social media, help, and other non-product pages
            if re.search(r'(facebook|twitter|instagram|linkedin|youtube|help|support|contact|about|privacy|terms|stories)', path):
                return False
                
            return True
            
        except Exception as e:
            logging.error(f"Error parsing URL {url}: {str(e)}")
            return False

    # async def crawl_page(self, page, domain: str, visited_urls: Set[str]):
    #     """Enhanced crawl_page method to handle dynamic content."""
    #     try:
    #         # Handle dynamic content loading
    #         await self.handle_dynamic_content(page) # Loads the dynamic content (if any) possible on the page
            
    #         # Get initial URLs
    #         all_urls = await self.extract_urls_from_page(page) # This could also be merged in handle_dynamic_content function but for the sake of seperation of concerns we will keep the functions seperate so they can complete their unique specified tasks.
            
    #         # Check if page might have infinite scroll
    #         page_height = await page.evaluate('document.documentElement.scrollHeight')
    #         viewport_height = await page.evaluate('window.innerHeight')
            
    #         if page_height > viewport_height * 2:  # Page is longer than 2 viewports
    #             # Handle potential infinite scroll
    #             scroll_urls = await self.handle_infinite_scroll(page)
    #             all_urls.update(scroll_urls)
            
    #         # Check for product pages
    #         product_match = await self.is_product_page(page)
    #         if product_match and product_match.confidence >= 0.7:
    #             self.product_urls[domain].add(product_match.url)
    #             logging.info(f"Found product URL: {product_match.url} "
    #                        f"(confidence: {product_match.confidence:.2f})")
            
    #         return [url for url in all_urls if self.is_same_domain(url, domain)]
            
    #     except Exception as e:
    #         logging.error(f"Error crawling {page.url}: {str(e)}")
    #         return []    # So that the program continues to run even if there is an error in the current page
    
    async def crawl_page(self, page, domain: str, visited_urls: Set[str]):
        """Modified crawl_page to check for product page first."""
        try:
            # First check if it's a product page
            product_match = await self.is_product_page(page)
            if product_match and product_match.confidence >= 0.7:
                self.product_urls[domain].add(product_match.url)
                logging.info(f"Found product URL: {product_match.url} "
                           f"(confidence: {product_match.confidence:.2f}, "
                           f"patterns: {', '.join(product_match.matched_patterns)})")
                return set()  # No need to crawl further if it's a product page

            # If not a product page, proceed with normal crawling
            await self.handle_dynamic_content(page)
            all_urls = await self.extract_urls_from_page(page)
            
            # Check for infinite scroll only if not a product page
            page_height = await page.evaluate('document.documentElement.scrollHeight')
            viewport_height = await page.evaluate('window.innerHeight')
            
            if page_height > viewport_height * 2:
                scroll_urls = await self.handle_infinite_scroll(page)
                all_urls.update(scroll_urls)
            
            return [url for url in all_urls if self.is_same_domain(url, domain)]
            
        except Exception as e:
            logging.error(f"Error crawling {page.url}: {str(e)}")
            return []

    async def handle_dynamic_content(self, page) -> bool:
        """
        Handle dynamically loaded content and ensure page is fully loaded.
        Returns True if successful.
        """
        try:
            # Wait for network to be idle
            await page.wait_for_load_state("networkidle", timeout=self.dynamic_wait * 1000)
            
            # Try different selectors one by one
            selectors = [
                '[data-product]',
                '.product',
                '[class*="product"]',
                '#products'
            ]
            
            for selector in selectors:
                try:
                    await page.wait_for_selector(selector, 
                                               state='visible',
                                               timeout=self.dynamic_wait * 1000)
                    return True
                except TimeoutError:
                    continue
            
            # Execute any pending JavaScript
            await page.evaluate('''
                () => new Promise((resolve) => {
                    requestAnimationFrame(() => {
                        setTimeout(resolve, 1000);
                    });
                })
            ''')
            
            return True
            
        except Exception as e:
            logging.error(f"Error handling dynamic content: {str(e)}")
            return False

    async def extract_urls_from_page(self, page) -> Set[str]:
        """Extract all URLs from the current page state."""
        try:
            links = await page.evaluate('''
                () => Array.from(
                    document.querySelectorAll('a[href]')
                ).map(a => a.href)
                .filter(href => href.startsWith('http'))
            ''')

            # Additional filtering for better URLs
            filtered_links = {
                link for link in links
                if not any(exclude in link.lower() for exclude in [
                    '/signin', '/login', '/cart', '/help', '/gp/', 
                    'customer-preferences', '/language', '/currency'
                ])
            }
            
            return filtered_links
        except Exception as e:
            logging.error(f"Error extracting URLs: {str(e)}")
            return set()

    async def handle_infinite_scroll(self, page) -> Set[str]:
        """
        Handle infinite scrolling pages by simulating scroll and waiting for new content.
        Returns a set of newly discovered URLs.
        """
        logging.info(f"Handling infinite scroll for {page.url}")
        all_urls = set()
        prev_height = 0
        scroll_attempts = 0
        start_time = datetime.now()
        
        try:
            while scroll_attempts < self.max_scroll_attempts:
                # Get current height
                current_height = await page.evaluate('document.documentElement.scrollHeight')
                
                if current_height == prev_height:
                    # Try to find and click "load more" buttons if present
                    for pattern in self.load_more_patterns:
                        button = await page.query_selector(
                            f'button:text-matches("{pattern}", "i"), '
                            f'a:text-matches("{pattern}", "i")'
                        )
                        if button:
                            try:
                                await button.click()
                                await page.wait_for_timeout(self.dynamic_wait * 1000)
                                break
                            except Exception as e:
                                logging.debug(f"Failed to click load more button: {str(e)}")
                    
                    # If no new content after button click, we're probably done
                    new_height = await page.evaluate('document.documentElement.scrollHeight')
                    if new_height == current_height:
                        break
                
                # Scroll to bottom
                await page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
                await page.wait_for_timeout(1000)  # Wait for content to load
                
                # Check for new content
                new_urls = await self.extract_urls_from_page(page)
                new_urls_count = len(new_urls - all_urls)
                all_urls.update(new_urls)
                
                logging.debug(f"Scroll attempt {scroll_attempts + 1}: Found {new_urls_count} new URLs")
                
                # Update for next iteration
                prev_height = current_height
                scroll_attempts += 1
                
                # Check timeout
                if (datetime.now() - start_time).seconds > self.scroll_timeout:
                    logging.warning(f"Scroll timeout reached for {page.url}")
                    break
                
                # If no new URLs found in consecutive attempts, stop scrolling
                if new_urls_count == 0:
                    scroll_attempts += 1
                else:
                    scroll_attempts = 0  # Reset counter if new URLs found
                
        except Exception as e:
            logging.error(f"Error during infinite scroll handling: {str(e)}")
        
        return all_urls

    # async def is_product_page(self, page) -> Optional[ProductUrlMatch]:
    #     """
    #     Advanced detection of product pages using multiple heuristics.
    #     Returns a ProductUrlMatch object if the page is likely a product page.
    #     """
    #     url = page.url
    #     current_url_lower = url.lower()
    #     matched_patterns = []
    #     confidence_score = 0
    #     pattern_matches = 0

    #     # Check URL patterns
    #     for pattern, score in self.url_patterns:
    #         if re.search(pattern, current_url_lower):
    #             confidence_score += score
    #             pattern_matches += 1
    #             matched_patterns.append(f"URL pattern: {pattern}")

    #     # Check page content patterns
    #     try:
    #         page_content = await page.content()
    #         content_matches = 0
    #         for pattern, score in self.content_patterns:
    #             if re.search(pattern, page_content, re.IGNORECASE):
    #                 confidence_score += score
    #                 content_matches += 1
    #                 matched_patterns.append(f"Content pattern: {pattern}")

    #         # Additional checks for structured data
    #         schema_org = await page.evaluate('''
    #             () => {
    #                 const elements = document.querySelectorAll('script[type="application/ld+json"]');
    #                 return Array.from(elements).map(el => el.textContent);
    #             }
    #         ''')
            
    #         for schema in schema_org:
    #             if '"@type": "Product"' in schema:
    #                 confidence_score += 1.0
    #                 matched_patterns.append("Schema.org Product markup")
    #                 break

    #         # Calculate final confidence score
    #         total_matches = pattern_matches + content_matches
    #         if total_matches > 0:
    #             confidence_score = confidence_score / total_matches
                
    #             if confidence_score >= 0.5:  # Minimum threshold
    #                 return ProductUrlMatch(url, confidence_score, matched_patterns)

    #     except Exception as e:
    #         logging.error(f"Error analyzing page content: {str(e)}")
    #         return None

    #     return None

    async def is_product_page(self, page) -> Optional[ProductUrlMatch]:
        """Enhanced product page detection for Amazon."""
        url = page.url
        current_url_lower = url.lower()
        matched_patterns = []
        confidence_score = 0
        pattern_matches = 0

        # Check if it's an Amazon page
        is_amazon = 'amazon' in current_url_lower

        # Apply appropriate patterns based on domain
        if is_amazon:
            # Check Amazon-specific URL patterns first
            for pattern, score in self.amazon_product_patterns:
                if re.search(pattern, current_url_lower):
                    confidence_score += score
                    pattern_matches += 1
                    matched_patterns.append(f"Amazon URL pattern: {pattern}")
            
            # Check Amazon-specific content patterns
            try:
                for pattern, score in self.amazon_content_patterns:
                    element = await page.query_selector(pattern)
                    if element:
                        confidence_score += score
                        pattern_matches += 1
                        matched_patterns.append(f"Amazon content pattern: {pattern}")
            except Exception as e:
                logging.error(f"Error checking Amazon content patterns: {str(e)}")
        else:
            # Use general patterns for non-Amazon sites
            for pattern, score in self.url_patterns:
                if re.search(pattern, current_url_lower):
                    confidence_score += score
                    pattern_matches += 1
                    matched_patterns.append(f"URL pattern: {pattern}")

            # Check page content patterns
            try:
                page_content = await page.content()
                for pattern, score in self.content_patterns:
                    if re.search(pattern, page_content, re.IGNORECASE):
                        confidence_score += score
                        pattern_matches += 1
                        matched_patterns.append(f"Content pattern: {pattern}")
            except Exception as e:
                logging.error(f"Error checking content patterns: {str(e)}")

        # Calculate final confidence score
        if pattern_matches > 0:
            confidence_score = confidence_score / pattern_matches
            if confidence_score >= 0.5:  # Minimum threshold
                return ProductUrlMatch(url, confidence_score, matched_patterns)

        return None

    def is_same_domain(self, url: str, domain: str) -> bool:
        """Check if URL belongs to the same domain."""
        try:
            parsed_url = urlparse(url)
            return domain in parsed_url.netloc
        except Exception as e:
            logging.error(f"Error parsing URL {url}: {str(e)}")
            return False

    async def handle_amazon_auth(self, page) -> bool:
        """Handle Amazon's CAPTCHA and authentication process."""
        try:
            # Check if we're on a CAPTCHA page
            captcha_selector = '#captchacharacters'
            try:
                await page.wait_for_selector(captcha_selector, timeout=5000)
                logging.info("CAPTCHA detected. Waiting for manual solving...")
                
                # Wait for CAPTCHA to be solved (determined by captcha field disappearing)
                await page.wait_for_selector(captcha_selector, state='hidden', timeout=120000)  # 2 minute timeout
                logging.info("CAPTCHA appears to be solved")
            except TimeoutError:
                logging.info("No CAPTCHA detected or CAPTCHA already solved")

            # Check if login is required
            sign_in_button = await page.query_selector('#nav-link-accountList, #nav-signin-tooltip .nav-action-button')
            
            if sign_in_button and self.amazon_credentials:
                logging.info("Login required. Attempting to sign in...")
                
                # Click sign in button
                await sign_in_button.click()
                await page.wait_for_selector('#ap_email')
                
                # Enter email
                await page.fill('#ap_email', self.amazon_credentials['email'])
                await page.click('#continue')
                
                # Enter password
                await page.wait_for_selector('#ap_password')
                await page.fill('#ap_password', self.amazon_credentials['password'])
                await page.click('#signInSubmit')
                
                # Wait for login to complete
                await page.wait_for_selector('#nav-link-accountList-nav-line-1:has-text("Hello")', 
                                        timeout=30000)
                logging.info("Successfully logged in to Amazon")
                return True
                
            return True  # Return True if no login was needed
            
        except Exception as e:
            logging.error(f"Error during Amazon authentication: {str(e)}")
            return False

    def save_results(self, filename: str = "product_urls.json"):
        """Save discovered URLs to a JSON file."""
        try:
            results = {
                domain: {
                    "urls": list(urls),
                    "count": len(urls),
                    "timestamp": datetime.now().isoformat()
                }
                for domain, urls in self.product_urls.items()
            }
            
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2)
            
            logging.info(f"Results saved to {filename}")
        except Exception as e:
            logging.error(f"Error saving results to {filename}: {str(e)}")

    async def is_captcha_present(self, page) -> bool:
        """Quick check for CAPTCHA presence."""
        try:
            captcha_selectors = [
                '#captchacharacters',
                'form[action*="validateCaptcha"]',
                'input[name="amzn-captcha-verify"]',
                'body:has-text("Enter the characters you see below")',
                'body:has-text("Type the characters you see in this image")'
            ]
            
            for selector in captcha_selectors:
                if await page.query_selector(selector):
                    return True
            return False
        except Exception as e:
            logging.error(f"Error checking for CAPTCHA: {str(e)}")
            return False

    async def handle_amazon_captcha(self, page) -> bool:
        """Handle Amazon CAPTCHA detection and waiting."""
        try:
            # Common CAPTCHA selectors
            captcha_selectors = [
                '#captchacharacters',
                'form[action*="validateCaptcha"]',
                'input[name="amzn-captcha-verify"]'
            ]
            
            # Check for CAPTCHA
            for selector in captcha_selectors:
                try:
                    is_captcha = await page.wait_for_selector(selector, timeout=5000)
                    if is_captcha:
                        logging.info("CAPTCHA detected. Waiting for manual solving...")
                        # Wait for CAPTCHA to be solved (wait for main content to appear)
                        await page.wait_for_selector('#nav-main, #navbar', timeout=300000)  # 5 minute timeout
                        logging.info("CAPTCHA appears to be solved")
                        return True
                except TimeoutError:
                    continue
            
            return True  # No CAPTCHA found
            
        except Exception as e:
            logging.error(f"Error during CAPTCHA handling: {str(e)}")
            return False


if __name__ == "__main__":
    domains = [
        "amazon.in",
        # "flipkart.com",
        # "myntra.com",
    ]
    
    amazon_credentials = {
        "email": "viragjain3010@gmail.com",
        "password": "WU7Pb_5PZBW4-72"
    }
    
    crawler = EcommerceCrawler(
        domains,
        amazon_credentials=amazon_credentials,
        scroll_timeout=30,
        max_scroll_attempts=10,
        dynamic_wait=5
    )
    asyncio.run(crawler.crawl_all_domains())
    crawler.save_results()
