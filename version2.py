import asyncio
import json
import logging
import re
from typing import Set, List, Dict
from urllib.parse import urljoin, urlparse
import aiohttp
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DomainCrawler:
    """Crawler for individual domain"""
    def __init__(self, domain: str, session: aiohttp.ClientSession, 
                 max_urls: int = 10000, max_depth: int = 10):
        self.domain = domain  # => "https://amazon.in"
        self.domain_name = urlparse(domain).netloc  # => "amazon.in"
        self.session = session
        self.max_urls = max_urls 
        self.max_depth = max_depth 
        self.visited_urls: Set[str] = set()
        self.product_urls: Set[str] = set()
        
        # Initialize Selenium
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # URL patterns
        self.product_patterns = [
            r'/product[s]?/',
            r'/item/',
            r'/p/',
            r'/dp/',
        ]

        # URL patterns to exclude
        self.exclude_patterns = [
            r'/career[s]?',
            r'/contact[-]?us',
            r'/about[-]?us',
            r'/login',
            r'/cart',
            r'/checkout',
            r'/account',
            r'/search',
            r'/privacy',
            r'/terms',
            r'/refund',
            r'/faq',
            r'/help',
            r'/payment[s]?',
            r'/order[s]?',
            r'/viewcart',
            r'/wishlist',
            r'/track',
            r'/signin',
            r'/signup',
            r'/register',
            r'/signout',
            r'/unsubscribe',
            r'/download',
            r'/support',
            r'/forum',
            r'/blog',
            r'/news',
            r'/article',
            r'/gallery',
            r'/media',
            r'/stories',
            r'/press',
            r'/events',
            r'/offer[s]?',
            r'/footer'
        ]

        # Domain-specific exclude patterns (Through observation)
        self.domain_specific_exclude_patterns = {
            "amazon.in": [
                r'/gp/',
                r'/s\?',  
                r'/b/'
                r'/b\?node=',  
                r'/prime',
                r'/customer-preferences',
                r'/minitv',
                r'/business',
                r'/now',
                r'/fresh',
                r'/deliveries',
            ],
            "flipkart.com": [
                r'/q/',
                r'gift-card-store',
                r'/returnpolicy',
                r'/helpcentre',
                r'/payments',
                r'/paymentsecurity',
                r'/shipping',
                r'/terms',
                r'/plus',
                r'/wishlist',
            ]
        }

        # Add domain-specific exclude patterns
        if self.domain_name in self.domain_specific_exclude_patterns:
            self.exclude_patterns.extend(self.domain_specific_exclude_patterns[self.domain_name])

    def is_product_url(self, url: str) -> bool:
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in self.product_patterns)

    def should_exclude_url(self, url: str) -> bool:
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in self.exclude_patterns)

    def get_url_depth(self, url: str) -> int:
        """Returns depth of URL by counting number of segments in path"""
        path = urlparse(url).path
        return len([x for x in path.split('/') if x])
    
    # TODO: convert url_depth to dfs like property rather than counting number of segments in path

    async def handle_dynamic_content(self, url: str) -> List[str]:
        """Handles dynamic content loaded via JavaScript e.g. infinite scroll, SPA's"""
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            links = set()
            scroll_attempts = 0
            max_scroll_attempts = 5

            while scroll_attempts < max_scroll_attempts:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)  # Replace asyncio.sleep with time.sleep for Selenium else error
                
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                elements = self.driver.find_elements(By.TAG_NAME, "a")
                
                for element in elements:
                    try:
                        link = element.get_attribute('href')
                        if link:
                            links.add(link)
                    except:
                        continue
                
                if new_height == last_height:
                    break
                    
                last_height = new_height
                scroll_attempts += 1
            
            return list(links)
            
        except Exception as e:
            logger.error(f"Error handling dynamic content for {url}: {str(e)}")
            return []

    async def crawl_url(self, url: str):
        """Crawls a URL and extracts product URLs from that page"""
        if url in self.visited_urls or self.should_exclude_url(url):
            return

        # Limit number of product URLs so as to stop the program from running indefinitely
        if len(self.product_urls) >= self.max_urls: 
            logger.info(f"[{self.domain}] Reached max URLs limit ({self.max_urls})")
            return

        if self.get_url_depth(url) > self.max_depth:
            return

        self.visited_urls.add(url)
        logger.info(f"[{self.domain}] Crawling: {url}")

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    soup = BeautifulSoup(text, 'html.parser')
                    
                    links = []
                    if "application/javascript" in response.headers.get('Content-Type', ''):
                        links = await self.handle_dynamic_content(url)
                    else:
                        links = [a.get('href') for a in soup.find_all('a', href=True)]
                    
                    tasks = []
                    for link in links:
                        if len(self.product_urls) >= self.max_urls:
                            break
                            
                        absolute_url = urljoin(self.domain, link)
                        if urlparse(absolute_url).netloc == urlparse(self.domain).netloc:
                            if self.is_product_url(absolute_url):
                                self.product_urls.add(absolute_url)
                            elif absolute_url not in self.visited_urls:
                                tasks.append(self.crawl_url(absolute_url))
                    
                    if tasks:
                        await asyncio.gather(*tasks) 
                
                elif response.status in [404, 502, 503]:
                    logger.warning(f"[{self.domain}] Error {response.status} for URL: {url}")
                
                elif response.status == 403:
                    logger.warning(f"[{self.domain}] Possible CAPTCHA at {url}")

                # TODO: Add a way to handle CAPTCHA (mostly manualy) and continue crawling

        except Exception as e:
            logger.error(f"[{self.domain}] Error crawling {url}: {str(e)}")

    async def start(self):
        try:
            await self.crawl_url(self.domain)
        finally:
            self.driver.quit()
        return list(self.product_urls) # Convert set to list for JSON else serialization error
    
class ParallelCrawler:
    """Main crawler that handles parallel processing of multiple domains"""
    def __init__(self, domains: List[str], output_file: str = 'product_urls.json',
                 max_urls_per_domain: int = 10000, max_depth: int = 10,
                 timeout_seconds: int = 3600):
        self.domains = domains
        self.output_file = output_file
        self.max_urls_per_domain = max_urls_per_domain
        self.max_depth = max_depth
        self.timeout_seconds = timeout_seconds
        self.results: Dict[str, List[str]] = {}

    async def crawl_all_domains(self):
        async with aiohttp.ClientSession() as session:
            tasks = []
            for domain in self.domains:
                crawler = DomainCrawler(
                    domain=domain,
                    session=session,
                    max_urls=self.max_urls_per_domain,
                    max_depth=self.max_depth
                )
                tasks.append(crawler.start())
            
            try:
                # Use asyncio.wait_for to implement timeout
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks), # .gather() is necessary for parallel crawling
                    timeout=self.timeout_seconds
                )
                
                # Store results
                for domain, urls in zip(self.domains, results):
                    self.results[domain] = urls
                
            except asyncio.TimeoutError:
                logger.warning(f"Crawling timed out after {self.timeout_seconds} seconds")
            except Exception as e:
                logger.error(f"Error during crawling: {str(e)}")
            
            # Save results regardless of completion
            self.save_results()

    def save_results(self):
        with open(self.output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to {self.output_file}")

    def run(self):
        try:
            asyncio.run(self.crawl_all_domains())
        except KeyboardInterrupt:
            logger.info("Crawler stopped by user")
            self.save_results()

# Example usage
if __name__ == "__main__":
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