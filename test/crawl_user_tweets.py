
import asyncio
import json
import sys
import argparse
import getpass
import re
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

# --- Helper Functions (copied from x/helper_functions.py and simplified) ---

def clean_text(text: str) -> str:
    """Clean and normalize text"""
    if not text:
        return ''
    text = ' '.join(text.split())
    text = text.replace('\x00', '')
    return text.strip()

def format_number(text: str) -> int:
    """Parse X number formats (1.2K, 3M, etc)"""
    if not text:
        return 0
    text = text.strip().upper()
    multipliers = {'': 1, 'K': 1_000, 'N': 1_000, 'M': 1_000_000, 'TR': 1_000_000, 'B': 1_000_000_000, 'T': 1_000_000_000}
    match = re.search(r'([\d.,]+)\s*([A-Z]{0,2})', text)
    if not match:
        return 0
    number_part, unit = match.groups()
    if '.' in number_part and ',' in number_part:
        number_part = number_part.replace('.', '').replace(',', '.')
    else:
        number_part = number_part.replace(',', '').replace('.', '.')
    try:
        value = float(number_part)
        return int(value * multipliers.get(unit, 1))
    except ValueError:
        return 0

def extract_tweet_id_from_url(url: str) -> Optional[str]:
    pattern = r'status/(\d+)'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def extract_hashtags(text: str) -> list:
    if not text: return []
    return re.findall(r'#(\w+)', text)

def extract_mentions(text: str) -> list:
    if not text: return []
    return re.findall(r'@(\w+)', text)

def extract_media_urls(tweet_element) -> list:
    media_urls = []
    # Images
    try:
        img_elements = tweet_element.query_selector_all('img[src*="media"]')
        for img in img_elements:
            src = img.get_attribute('src')
            if src and 'profile_images' not in src:
                media_urls.append(src)
    except: pass
    
    # Videos
    try:
        video_elements = tweet_element.query_selector_all('video')
        for video in video_elements:
            src = video.get_attribute('src')
            if src:
                media_urls.append(src)
    except: pass
    return media_urls

# --- Parser Class (adapted from x/parser.py) ---

class TweetParser:
    def parse_single_tweet_element(self, element, page) -> Optional[Dict]:
        try:
            tweet_data = {}
            
            # Author username
            username_elem = element.query_selector('[data-testid="User-Name"] a[role="link"]')
            if username_elem:
                href = username_elem.get_attribute('href')
                if href:
                    tweet_data['author_username'] = href.strip('/').split('/')[-1]
            
            # Text
            text_elem = element.query_selector('[data-testid="tweetText"]')
            if text_elem:
                tweet_text = clean_text(text_elem.inner_text())
                tweet_data['text'] = tweet_text
                tweet_data['hashtags'] = extract_hashtags(tweet_text)
                tweet_data['mentions'] = extract_mentions(tweet_text)
            else:
                tweet_data['text'] = ''
                tweet_data['hashtags'] = []
                tweet_data['mentions'] = []

            # URL and ID via Time element
            time_elem = element.query_selector('time')
            if time_elem:
                # 1. Posted time
                datetime_str = time_elem.get_attribute('datetime')
                if datetime_str:
                    tweet_data['posted_at'] = datetime_str

                # 2. URL extraction
                try:
                    # Try getting parent anchor tag
                    tweet_url = time_elem.evaluate("""(element) => {
                        const link = element.closest('a');
                        return link ? link.getAttribute('href') : null;
                    }""")
                    if tweet_url:
                        full_url = f"https://x.com{tweet_url}" if not tweet_url.startswith('http') else tweet_url
                        tweet_data['url'] = full_url
                        tweet_data['tweet_id'] = extract_tweet_id_from_url(full_url)
                except Exception as e:
                    # Fallback logic if needed
                    pass
            
            # Fallback for ID if still missing
            if not tweet_data.get('tweet_id'):
                all_links = element.query_selector_all('a[href*="/status/"]')
                for link in all_links:
                    href = link.get_attribute('href')
                    if href and '/status/' in href:
                        full_url = f"https://x.com{href}" if not href.startswith('http') else href
                        tweet_id = extract_tweet_id_from_url(full_url)
                        if tweet_id:
                            tweet_data['url'] = full_url
                            tweet_data['tweet_id'] = tweet_id
                            break

            # Engagement
            self._parse_engagement(element, tweet_data)
            
            # Media
            tweet_data['media_urls'] = extract_media_urls(element)

            if tweet_data.get('tweet_id') or tweet_data.get('text'):
                return tweet_data
            return None

        except Exception as e:
            # print(f"Error parsing tweet element: {e}")
            return None

    def _parse_engagement(self, element, data):
        metrics = {'replies': '[data-testid="reply"]', 'retweets': '[data-testid="retweet"]', 'likes': '[data-testid="like"]'}
        for key, selector in metrics.items():
            elem = element.query_selector(selector)
            if elem:
                label = elem.get_attribute('aria-label')
                if label:
                    parts = label.split()
                    if parts:
                        data[key] = format_number(parts[0])
            else:
                 data[key] = 0
        
        # Views
        views_elem = element.query_selector('a[href*="/analytics"]')
        if views_elem:
             data['views'] = format_number(clean_text(views_elem.inner_text()))
        else:
             data['views'] = 0

# --- Main Script ---

from playwright.async_api import async_playwright

async def manual_login(page, session_file):
    print("\n" + "="*60)
    print("MANUAL LOGIN REQUIRED (To avoid bot detection)")
    print("="*60)
    print("1. The browser will open shortly.")
    print("2. Please log in to your X account manually in the opened window.")
    print("3. After you are effectively logged in, come back here and press ENTER.")
    print("="*60 + "\n")
    
    await page.goto("https://x.com/i/flow/login")
    
    # Wait for user confirmation in terminal
    await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter after you have logged in successfully...")
    
    # Check if logged in
    try:
        # Just check for 'home' in url or a post element
        if "home" in page.url or await page.query_selector('[data-testid="Tweet-User-Avatar"]'):
            print("Login verified!")
            await page.context.storage_state(path=session_file)
            print(f"Session saved to {session_file}")
            return True
        else:
            print("Could not verify login. Proceeding anyway.")
            return False
    except Exception as e:
        print(f"Error verifying login: {e}")
        return False

async def crawl_tweets(username: str, limit: int = 50, headless: bool = False, do_login_flag: bool = False, days: int = None, since: str = None, session_file: str = "session.json"):
    
    cutoff_date = None
    if days:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        print(f"Filtering tweets from the last {days} days (since {cutoff_date.isoformat()})")
    elif since:
        try:
            ts_clean = since.replace('Z', '+00:00')
            cutoff_date = datetime.fromisoformat(ts_clean).replace(tzinfo=timezone.utc)
            print(f"Filtering tweets since {cutoff_date.isoformat()}")
        except Exception as e:
            print(f"Error parsing date '{since}': {e}")
            return

    parser = TweetParser()
    data = []
    
    async with async_playwright() as p:
        # Load storage state if exists and not forcing new login
        storage_state = session_file
        if do_login_flag or not Path(session_file).exists():
            storage_state = None
            
        print(f"Launching browser (Headless: {headless})...")
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            storage_state=storage_state if storage_state else None
        )
        page = await context.new_page()

        # Handle Login
        if do_login_flag:
            await manual_login(page, session_file)
        elif not storage_state:
            print("No session file found. Running as guest (limited view). Use --login to authenticate.")

        # Navigate
        url = f"https://x.com/{username}"
        print(f"Navigating to {url}...")
        try:
            await page.goto(url, timeout=60000)
            await page.wait_for_timeout(3000) # Initial load wait
        except Exception as e:
            print(f"Error navigating: {e}")
            return

        # Check if page loaded
        if await page.query_selector('text="This account doesn’t exist"'):
            print("Account does not exist.")
            return

        tweets_seen = set()
        consecutive_old_tweets = 0
        max_consecutive = 5
        
        last_height = await page.evaluate("document.body.scrollHeight")
        scroll_attempts = 0
        
        while len(data) < limit:
            # Parse visible tweets
            elements = await page.query_selector_all('[data-testid="tweet"]')
            
            # Log progress
            # print(f"Found {len(elements)} visible elements")

            for el in elements:
                t = parser.parse_single_tweet_element(el, page)
                if not t: continue
                
                # Check uniqueness
                tid = t.get('tweet_id')
                if not tid:
                    # Fallback unique key
                    tid = t.get('text', '')[:30] + t.get('posted_at', '')
                    
                if tid in tweets_seen:
                    continue
                
                # Date Check
                if cutoff_date and t.get('posted_at'):
                    try:
                        # Normalize date
                        ts_str = t['posted_at'].replace('Z', '+00:00')
                        t_date = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
                        
                        if t_date < cutoff_date:
                            consecutive_old_tweets += 1
                            if consecutive_old_tweets >= max_consecutive:
                                print(f"Reached tweets older than {cutoff_date}. Stopping...")
                                # Save what we have
                                break
                            
                            # Skip this old tweet
                            continue
                        else:
                            consecutive_old_tweets = 0 # Reset if we find a new one
                    except Exception as e:
                        # If can't parse date, keep it just in case
                        pass
                
                tweets_seen.add(tid)
                data.append(t)
                # Prepare log message safe for f-string
                safe_text = t.get('text', '')[:50].replace('\n', ' ')
                print(f"[{len(data)}] {t.get('posted_at', '?')} - {safe_text}...")
                
                if len(data) >= limit:
                    break
            
            if len(data) >= limit or consecutive_old_tweets >= max_consecutive:
                break

            # Scroll
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000 + random.random() * 2000) # Human delay
            
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
                if scroll_attempts > 3:
                     print("End of Page or Stuck.")
                     break
            else:
                scroll_attempts = 0
                last_height = new_height
        
        await browser.close()

    # Save
    filename = f"tweets_{username}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Done. Saved {len(data)} tweets to {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("username", help="Twitter handle")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--login", action="store_true", help="Perform manual login to save session")
    parser.add_argument("--days", type=int)
    parser.add_argument("--since", type=str)
    parser.add_argument("--session", type=str, default="session.json")
    
    args = parser.parse_args()
    asyncio.run(crawl_tweets(args.username, args.limit, args.headless, args.login, args.days, args.since, args.session))
