#!/usr/bin/env python3
import os
import re
import time
import sys
import logging
import openpyxl
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    WebDriverException,
)

# ---------------- CONFIG ----------------
NAUKRI_EMAIL = os.getenv("NAUKRI_EMAIL", "ameypatankar333@gmail.com")
NAUKRI_PASSWORD = os.getenv("NAUKRI_PASSWORD", "9773051915")
SKILLS = os.getenv("SKILLS", "Java and Spring Boot And React")
EXPERIENCE = os.getenv("EXPERIENCE", "11")  # years
EXCEL_FILE = os.getenv("EXCEL_FILE", "applied_jobs.xlsx")
MIN_EXPECTED_SALARY = float(os.getenv("MIN_EXPECTED_SALARY", "25"))  # LPA
MAX_APPLY = int(os.getenv("MAX_APPLY", "50"))  # Number of successful applications to reach
CHROME_DRIVER_PATH = os.getenv("CHROME_DRIVER_PATH", "")  # optional
HEADLESS = True  # <-- Visible browser for local debugging

LOGIN_URL = "https://www.naukri.com/nlogin/login"
SEARCH_URL = "https://www.naukri.com/jobs-in-india"

# ---------------- LOGGING ----------------
logging.basicConfig(
    filename="naukri_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.info("Script started")
print("Script started (visible browser). Check naukri_log.txt for detail.")

# ---------------- EXCEL SETUP ----------------
try:
    wb = openpyxl.load_workbook(EXCEL_FILE)
    sheet = wb.active
    logging.info(f"Loaded existing Excel: {EXCEL_FILE}")
except Exception:
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["Job ID", "Job Title", "Company", "Salary", "Job Link", "Status"])
    logging.info(f"Created new Excel: {EXCEL_FILE}")

existing_job_ids = {str(row[0]) for row in sheet.iter_rows(min_row=2, values_only=True) if row and row[0] is not None}

# ---------------- SELENIUM SETUP ----------------
options = Options()
if HEADLESS:
    options.add_argument("--headless=new")  # headless mode
    options.add_argument("--no-sandbox")  # already there, needed for Linux CI
    options.add_argument("--disable-dev-shm-usage")  # avoid shared memory issue
    options.add_argument("--disable-gpu")  # required in some headless setups
    options.add_argument("--window-size=1920,1080")  # force proper viewport
    options.add_argument("--remote-debugging-port=9222")  # helps debugging
else:
    options.add_argument("--start-maximized")

# helpful flags
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                     "AppleWebKit/537.36 (KHTML, like Gecko)"
                     "Chrome/116.0.5845.140 Safari/537.36")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
options.add_argument("--disable-extensions")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

# start driver (use CHROME_DRIVER_PATH if provided)
driver = None
try:
    if CHROME_DRIVER_PATH:
        from selenium.webdriver.chrome.service import Service
        service = Service(CHROME_DRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)
except WebDriverException as e:
    logging.error(f"Could not start ChromeDriver: {e}")
    print("ERROR: Could not start ChromeDriver:", e)
    sys.exit(1)

wait = WebDriverWait(driver, 40)
actions = ActionChains(driver)

# ---------------- HELPERS ----------------
def safe_click(element, timeout=8):
    """Scroll to element, wait until it is clickable (rough), then click via ActionChains."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        end = time.time() + timeout
        while time.time() < end:
            try:
                if element.is_displayed() and element.is_enabled():
                    break
            except StaleElementReferenceException:
                return False
            time.sleep(0.12)
        actions.move_to_element(element).pause(0.12).click().perform()
        return True
    except (ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException, Exception) as exc:
        logging.warning(f"safe_click failed: {exc}")
        return False

def parse_max_salary(salary_text):
    """Try to parse max salary in LPA. Return float or None."""
    if not salary_text:
        return None
    s = salary_text.lower()
    if "not disclose" in s or "not disclosed" in s:
        return None
    s = s.replace("lacs pa", "lpa").replace("lacs", "lpa").replace("per annum", "").replace("p.a.", "").replace("pa", "")
    nums = re.findall(r"[\d\.]+", s)
    if not nums:
        return None
    try:
        val = float(nums[-1])
        return val
    except Exception:
        return None

def save_record(job_id, title, company, salary_text, job_link, status):
    """Append row to Excel and save immediately, mark id processed."""
    try:
        sheet.append([str(job_id), title, company, salary_text, job_link, status])
        wb.save(EXCEL_FILE)
    except Exception as e:
        logging.error("Failed to write to Excel: %s", e)
    existing_job_ids.add(str(job_id))
    print(f"Recorded: {title} | {company} | {status}")

# ---------------- MAIN FLOW ----------------
try:
    # ---------- LOGIN ----------
    logging.info("Opening login page")
    print("Opening login page...")
    driver.get(LOGIN_URL)
    try:
        wait.until(EC.presence_of_element_located((By.ID, "usernameField")))
    except TimeoutException:
        driver.save_screenshot("login_page_not_loaded.png")
        logging.error("Login page did not load usernameField; exiting.")
        raise SystemExit("Login field not found")

    try:
        username_input = driver.find_element(By.ID, "usernameField")
        password_input = driver.find_element(By.ID, "passwordField")
        username_input.clear()
        username_input.send_keys(NAUKRI_EMAIL)
        password_input.clear()
        password_input.send_keys(NAUKRI_PASSWORD)
        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        print("Submitting login...")
        if not safe_click(submit_btn):
            try:
                submit_btn.click()
            except Exception:
                pass
        logging.info("Login submitted")
        time.sleep(4)
    except Exception as e:
        driver.save_screenshot("login_error.png")
        logging.error(f"Login error: {e}", exc_info=True)
        raise

    # ---------- SEARCH ----------
    logging.info("Navigating to job search page")
    print("Navigating to job search page...")
    driver.get(SEARCH_URL)
    time.sleep(2)
    try:
        search_bar_container = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "nI-gNb-sb__main")))
        safe_click(search_bar_container)
        search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Enter keyword / designation / companies']")))
        search_box.clear()
        search_box.send_keys(SKILLS)
        exp_dropdown = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='dropdownMainContainer']")))
        safe_click(exp_dropdown)
        exp_option = wait.until(EC.element_to_be_clickable((By.XPATH, f"//li[@title='{EXPERIENCE} years']")))
        safe_click(exp_option)
        search_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@class='nI-gNb-sb__icon-wrapper']")))
        safe_click(search_button)
        logging.info("Search executed")
        print("Search executed, waiting for results...")
        time.sleep(4)
    except Exception as e:
        driver.save_screenshot("search_error.png")
        logging.error(f"Job search failed: {e}", exc_info=True)
        raise

    # ---------- MAIN LOOP (pages -> jobs) ----------
    applied_count = 0
    page_num = 1
    visited_pages = set()
    print(f"Starting job processing (target apply count = {MAX_APPLY})")

    while applied_count < MAX_APPLY:
        logging.info(f"Processing page {page_num}")
        print(f"\n--- Processing page {page_num} --- (applied so far: {applied_count})")
        current_url = driver.current_url
        if current_url in visited_pages:
            logging.info("Already visited this page URL; stopping to avoid loop.")
            break
        visited_pages.add(current_url)

        # Prefer job container inside chatbot wrapper if present
        jobs = []
        try:
            container = driver.find_element(By.CLASS_NAME, "chatbot_DrawerContentWrapper")
            jobs = container.find_elements(By.XPATH, ".//div[contains(@class,'srp-jobtuple-wrapper') or contains(@class,'jobTuple')]")
            logging.info("Found job container inside chatbot_DrawerContentWrapper")
        except Exception:
            # fallback to site-wide job cards
            jobs = driver.find_elements(By.XPATH, "//div[contains(@class,'srp-jobtuple-wrapper') or contains(@class,'jobTuple')]")

        if not jobs:
            logging.info("No job cards found on this page. Ending.")
            print("No job cards found on this page. Ending.")
            break

        # iterate by index to avoid stale-element issues
        idx = 0
        while idx < len(jobs) and applied_count < MAX_APPLY:
            # Re-fetch job list each iteration
            try:
                jobs = driver.find_elements(By.XPATH, "//div[contains(@class,'srp-jobtuple-wrapper') or contains(@class,'jobTuple')]")
                job = jobs[idx]
            except Exception:
                idx += 1
                continue
            idx += 1

            # get job id
            try:
                job_id = job.get_attribute("data-job-id")
            except StaleElementReferenceException:
                continue

            if not job_id:
                continue
            if str(job_id) in existing_job_ids:
                # skip already processed
                continue

            # extract fields
            try:
                title_elem = job.find_element(By.XPATH, ".//a[contains(@class,'title')]")
                title = title_elem.text.strip()
                job_link = title_elem.get_attribute("href")
            except Exception:
                title = "Unknown Title"
                job_link = "N/A"

            try:
                company = job.find_element(By.XPATH, ".//a[contains(@class,'comp-name') or contains(@class,'subTitle')]").text.strip()
            except Exception:
                company = "Unknown Company"

            try:
                salary_text = job.find_element(By.XPATH, ".//span[contains(@class,'sal-wrap')]").text.strip()
            except Exception:
                salary_text = "Not Disclosed"

            print(f"Found job: {title} | {company} | {salary_text} | ID: {job_id}")
            logging.info(f"Found job: {job_id} | {title} | {company} | {salary_text}")

            # If job card indicates Already Applied -> record and skip (do not increment)
            try:
                applied_tag = job.find_element(By.XPATH, ".//span[contains(text(),'Applied')]")
                if applied_tag.is_displayed():
                    save_record(job_id, title, company, salary_text, job_link, "Already Applied")
                    logging.info(f"Card shows Already Applied for {job_id} — recorded and skipped")
                    continue
            except Exception:
                pass

            # Salary filter
            max_sal = parse_max_salary(salary_text)
            if (max_sal is not None) and (max_sal < MIN_EXPECTED_SALARY):
                save_record(job_id, title, company, salary_text, job_link, "Skipped (Low Salary)")
                logging.info(f"Skipped low salary job {job_id}: {salary_text}")
                continue

            # Open job detail (click title) - may open new tab
            try:
                if not safe_click(title_elem):
                    try:
                        title_elem.click()
                    except Exception:
                        save_record(job_id, title, company, salary_text, job_link, "Could not open job detail")
                        continue
                time.sleep(1)
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                time.sleep(1)
            except Exception as e:
                logging.error(f"Error opening job detail for {job_id}: {e}", exc_info=True)
                save_record(job_id, title, company, salary_text, job_link, f"Open detail error: {e}")
                try:
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                except Exception:
                    pass
                continue

            # find apply button on detail page (buttons or links containing 'apply')
            apply_btn = None
            try:
                candidates = driver.find_elements(By.XPATH, "//button|//a")
                for b in candidates:
                    try:
                        txt = (b.text or "").strip().lower()
                        if "apply" in txt and b.is_displayed() and b.is_enabled():
                            apply_btn = b
                            break
                    except Exception:
                        continue
            except Exception:
                apply_btn = None

            if not apply_btn:
                save_record(job_id, title, company, salary_text, job_link, "No Apply Button")
                logging.info(f"No apply button on detail for {job_id}")
                # close detail tab if opened
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                else:
                    try:
                        driver.back()
                    except Exception:
                        pass
                continue

            btn_text = (apply_btn.text or "").strip().lower()

            # Skip company-site applies
            if "company site" in btn_text or "apply on company" in btn_text:
                save_record(job_id, title, company, salary_text, job_link, "Skipped (Company Site)")
                logging.info(f"Skipped company-site job {job_id}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                else:
                    try:
                        driver.back()
                    except Exception:
                        pass
                continue

            # If button already says "Applied"
            if "applied" in btn_text:
                save_record(job_id, title, company, salary_text, job_link, "Already Applied")
                logging.info(f"Detail shows Already Applied for {job_id}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                else:
                    try:
                        driver.back()
                    except Exception:
                        pass
                continue

            # Click apply
            clicked = safe_click(apply_btn)
            if not clicked:
                try:
                    apply_btn.click()
                except Exception as e:
                    save_record(job_id, title, company, salary_text, job_link, "No Apply Button / Not Clickable")
                    logging.warning(f"Could not click apply for {job_id}: {e}")
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    else:
                        try:
                            driver.back()
                        except Exception:
                            pass
                    continue

            # After clicking check for chatbot drawer (short wait)
            time.sleep(1.5)
            chatbot_shown = False
            try:
                # short explicit wait for chatbot drawer presence
                small_wait = WebDriverWait(driver, 3)
                small_wait.until(EC.presence_of_element_located((By.CLASS_NAME, "chatbot_DrawerContentWrapper")))
                # if found and visible, mark skipped
                chatbot_el = driver.find_element(By.CLASS_NAME, "chatbot_DrawerContentWrapper")
                if chatbot_el and chatbot_el.is_displayed():
                    chatbot_shown = True
            except Exception:
                chatbot_shown = False

            if chatbot_shown:
                save_record(job_id, title, company, salary_text, job_link, "Skipped (Chatbot)")
                logging.info(f"Chatbot appeared for {job_id}; skipped")
                # close tab or go back
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                else:
                    try:
                        driver.back()
                    except Exception:
                        pass
                # do not increment applied_count
                continue

            # No chatbot — assume success if no error (try to detect 'Applied' label)
            status = "Applied Successfully"
            try:
                # re-evaluate apply button text if available
                try:
                    new_text = (apply_btn.text or "").strip().lower()
                except Exception:
                    new_text = ""
                if "applied" in new_text:
                    status = "Applied Successfully"
            except Exception:
                status = "Applied Successfully"

            save_record(job_id, title, company, salary_text, job_link, status)
            applied_count += 1
            logging.info(f"Applied to {job_id} — total applied {applied_count}")

            # close detail tab or navigate back to results
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                else:
                    driver.back()
            except Exception:
                pass

            # short human-like delay
            time.sleep(1.2)

        # ---------- PAGINATION ----------
        if applied_count >= MAX_APPLY:
            logging.info(f"Reached MAX_APPLY ({MAX_APPLY}). Ending.")
            break

        logging.info("Attempting pagination (numbered pages -> Next fallback)")
        # Try numbered pages first (div.lastCompMark -> div.styles_pages__v1rAK a)
        next_clicked = False
        try:
            pagination_container = driver.find_element(By.CSS_SELECTOR, "div.lastCompMark div.styles_pages__v1rAK")
            links = pagination_container.find_elements(By.TAG_NAME, "a")
            # build mapping number->href for numeric links
            page_map = {}
            for link in links:
                txt = (link.text or "").strip()
                href = link.get_attribute("href")
                if txt.isdigit() and href:
                    try:
                        num = int(txt)
                        page_map[num] = href
                    except Exception:
                        continue
            # prefer page_num+1 if available, else smallest > page_num
            target_href = None
            if (page_num + 1) in page_map:
                target_href = page_map[page_num + 1]
            else:
                greater = [n for n in sorted(page_map.keys()) if n > page_num]
                if greater:
                    target_href = page_map[greater[0]]
            if target_href:
                logging.info(f"Going to next numeric page: {target_href}")
                driver.get(target_href)
                # wait until URL changes (safety)
                try:
                    WebDriverWait(driver, 8).until(lambda d: d.current_url != current_url)
                except Exception:
                    logging.info("URL didn't change after numeric page click; continuing anyway.")
                page_num += 1
                time.sleep(3)
                next_clicked = True
        except Exception:
            next_clicked = False

        if not next_clicked:
            # Fallback to Next link/button
            try:
                next_btn = driver.find_element(By.XPATH, "//a[contains(text(),'Next') or contains(., 'Next')]")
                if safe_click(next_btn) or True:
                    try:
                        WebDriverWait(driver, 8).until(lambda d: d.current_url != current_url)
                    except Exception:
                        logging.info("URL didn't change after Next click")
                    page_num += 1
                    time.sleep(3)
                    next_clicked = True
            except Exception:
                next_clicked = False

        if not next_clicked:
            logging.info("No next page found; ending pagination.")
            print("No next page found; ending.")
            break

    # Done main loop
    logging.info(f"Completed. Total applied: {applied_count}")
    print(f"\nDone. Applied {applied_count} jobs. Excel: {EXCEL_FILE}")
    try:
        wb.save(EXCEL_FILE)
    except Exception:
        logging.warning("Failed to save Excel at final step.")
    driver.quit()

except Exception as fatal:
    logging.exception("Fatal error during script execution")
    print(f"Fatal error: {fatal}. See naukri_log.txt and screenshots.")
    try:
        driver.save_screenshot("fatal_error.png")
    except Exception:
        pass
    try:
        wb.save(EXCEL_FILE)
    except Exception:
        pass
finally:
    try:
        if driver:
            driver.quit()
    except Exception:
        pass
    logging.info("Script finished (final).")
