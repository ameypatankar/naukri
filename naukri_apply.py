#!/usr/bin/env python3
import os
import re
import time
import sys
import logging
import openpyxl
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
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
# Prefer environment variables for credentials (set these in GitHub Actions as secrets)
NAUKRI_EMAIL = os.getenv("NAUKRI_EMAIL", "ameypatankar333@gmail.com")
NAUKRI_PASSWORD = os.getenv("NAUKRI_PASSWORD", "9773051915")

SKILLS = os.getenv("SKILLS", "Java and Spring Boot And React")
EXPERIENCE = os.getenv("EXPERIENCE", "11")  # years
EXCEL_FILE = os.getenv("EXCEL_FILE", "applied_jobs.xlsx")
MIN_EXPECTED_SALARY = float(os.getenv("MIN_EXPECTED_SALARY", "25"))  # LPA
MAX_APPLY = int(os.getenv("MAX_APPLY", "50"))  # Number of successful applications to attempt

# Optional: path to chromedriver binary (leave empty to use PATH)
CHROME_DRIVER_PATH = os.getenv("CHROME_DRIVER_PATH", "")

# Headless mode true for CI / GitHub Actions
HEADLESS = True

LOGIN_URL = "https://www.naukri.com/nlogin/login"
SEARCH_URL = "https://www.naukri.com/jobs-in-india"

# ---------------- LOGGING ----------------
logging.basicConfig(
    filename="naukri_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.info("Script started")
print("Script started (headless). Check naukri_log.txt for details.")

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

# Load existing job IDs to avoid duplicates
existing_job_ids = set()
for row in sheet.iter_rows(min_row=2, values_only=True):
    if row[0] is not None:
        existing_job_ids.add(str(row[0]))

# ---------------- SELENIUM SETUP ----------------
options = Options()
if HEADLESS:
    options.add_argument("--headless=new")
else:
    options.add_argument("--start-maximized")

# Stability flags for CI / headless
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--disable-software-rasterizer")
options.add_argument("--disable-accelerated-2d-canvas")
options.add_argument("--window-size=1920,1080")
options.add_argument("--disable-extensions")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-logging")
options.add_argument("--log-level=3")
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/116.0.5845.188 Safari/537.36"
)
# reduce automation fingerprint
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = None
try:
    if CHROME_DRIVER_PATH:
        service = Service(CHROME_DRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)
except WebDriverException as e:
    logging.error(f"Could not start ChromeDriver: {e}")
    print(f"ERROR: Could not start ChromeDriver: {e}")
    sys.exit(1)

wait = WebDriverWait(driver, 20)
actions = ActionChains(driver)

# ---------------- HELPERS ----------------
def safe_click(element, timeout=8):
    """Scroll to element, wait until it appears enabled, then click via ActionChains."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        end = time.time() + timeout
        while time.time() < end:
            try:
                if element.is_displayed() and element.is_enabled():
                    break
            except StaleElementReferenceException:
                return False
            time.sleep(0.2)
        actions.move_to_element(element).pause(0.15).click().perform()
        return True
    except (ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException, Exception) as exc:
        logging.warning(f"safe_click failed: {exc}")
        return False

def parse_max_salary(salary_text):
    """Try to extract a numeric maximum salary in LPA from salary_text. Returns float or None."""
    if not salary_text:
        return None
    low = salary_text.lower()
    if "not disclose" in low or "not disclosed" in low:
        return None
    # Normalize common tokens
    s = salary_text.lower().replace("lacs pa", "lpa").replace("lacs p.a.", "lpa").replace("lacs", "lpa")
    s = s.replace("per annum", "").replace("pa", "").replace("p.a.", "")
    # find numbers
    nums = re.findall(r"[\d\.]+", s)
    if not nums:
        return None
    try:
        val = float(nums[-1])
        # assume LPA if text mentions lpa or lac
        if "lpa" in s or "lac" in s or "lacs" in s:
            return val
        # fallback: if huge number assume it's in lakhs or rupees - but best effort
        return val
    except Exception:
        return None

def save_job_record(job_id, title, company, salary_text, job_link, status):
    """Append to excel and save immediately."""
    try:
        sheet.append([str(job_id), title, company, salary_text, job_link, status])
        wb.save(EXCEL_FILE)
    except Exception as e:
        logging.error(f"Failed to write to Excel: {e}")

# ---------------- MAIN FLOW ----------------
try:
    # ---------- LOGIN ----------
    logging.info("Opening login page")
    driver.get(LOGIN_URL)
    time.sleep(2)

    try:
        wait.until(EC.presence_of_element_located((By.ID, "usernameField")))
    except TimeoutException:
        driver.save_screenshot("login_page_not_loaded.png")
        logging.error("Login page did not load usernameField; exiting.")
        raise SystemExit("Login field not found")

    # Fill credentials and submit
    try:
        username_input = driver.find_element(By.ID, "usernameField")
        password_input = driver.find_element(By.ID, "passwordField")
        username_input.clear()
        username_input.send_keys(NAUKRI_EMAIL)
        password_input.clear()
        password_input.send_keys(NAUKRI_PASSWORD)
        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        if not safe_click(submit_btn):
            try:
                submit_btn.click()
            except Exception:
                pass
        logging.info("Login submitted")
        # wait a bit for redirect
        time.sleep(4)
    except Exception as e:
        driver.save_screenshot("login_error.png")
        logging.error(f"Login error: {e}", exc_info=True)
        raise

    # ---------- SEARCH ----------
    logging.info("Navigating to job search page")
    driver.get(SEARCH_URL)
    time.sleep(2)
    try:
        # click search container to focus
        search_bar_container = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "nI-gNb-sb__main")))
        safe_click(search_bar_container)
        search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Enter keyword / designation / companies']")))
        search_box.clear()
        search_box.send_keys(SKILLS)

        # set experience
        exp_dropdown = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='dropdownMainContainer']")))
        safe_click(exp_dropdown)
        exp_option = wait.until(EC.element_to_be_clickable((By.XPATH, f"//li[@title='{EXPERIENCE} years']")))
        safe_click(exp_option)

        # click search
        search_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@class='nI-gNb-sb__icon-wrapper']")))
        safe_click(search_button)
        logging.info("Search executed")
        time.sleep(4)
    except Exception as e:
        driver.save_screenshot("search_error.png")
        logging.error(f"Job search failed: {e}", exc_info=True)
        raise

    # ---------- MAIN LOOP (pages -> jobs) ----------
    applied_count = 0
    page_num = 1

    while applied_count < MAX_APPLY:
        logging.info(f"Processing page {page_num} (applied so far: {applied_count})")
        # find job cards - use robust xpath that covers variants
        try:
            jobs = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[@class='srp-jobtuple-wrapper' or contains(@class,'jobTuple')]")))
        except TimeoutException:
            logging.info("No job cards found on this page. Ending loop.")
            break

        if not jobs:
            logging.info("Job list empty; ending.")
            break

        # iterate by index to reduce stale-element issues
        total_jobs_on_page = len(jobs)
        index = 0
        while index < total_jobs_on_page and applied_count < MAX_APPLY:
            # re-fetch job list each iteration
            try:
                jobs = driver.find_elements(By.XPATH, "//div[@class='srp-jobtuple-wrapper' or contains(@class,'jobTuple')]")
                job = jobs[index]
            except Exception:
                index += 1
                continue

            index += 1  # increase index for next iteration (we only increment applied_count for actual applied)

            try:
                job_id = job.get_attribute("data-job-id")
            except StaleElementReferenceException:
                continue

            if not job_id:
                continue

            if str(job_id) in existing_job_ids:
                # skip duplicates (do not increment applied_count)
                logging.debug(f"Duplicate job id {job_id} — skipping")
                continue

            # extract details safely
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

            logging.info(f"Job found: {job_id} | {title} | {company} | {salary_text}")

            # if applied tag present on card, record and skip (do not increment applied_count)
            try:
                applied_tag = job.find_element(By.XPATH, ".//span[contains(text(),'Applied')]")
                if applied_tag.is_displayed():
                    status = "Already Applied"
                    save_job_record = save_job_record if 'save_job_record' in globals() else None
                    sheet.append([str(job_id), title, company, salary_text, job_link, status])
                    wb.save(EXCEL_FILE)
                    existing_job_ids.add(str(job_id))
                    logging.info(f"Card shows Already Applied for {job_id} — recorded and skipped")
                    continue
            except Exception:
                pass

            # Salary filter
            max_sal = parse_max_salary(salary_text)
            if (max_sal is not None) and (max_sal < MIN_EXPECTED_SALARY):
                status = "Skipped (Low Salary)"
                sheet.append([str(job_id), title, company, salary_text, job_link, status])
                wb.save(EXCEL_FILE)
                existing_job_ids.add(str(job_id))
                logging.info(f"Skipped low salary job {job_id}: {salary_text}")
                continue

            # Open job details (click title) and switch to new tab if any
            try:
                # try clicking the title element
                try:
                    clickable = title_elem
                except Exception:
                    clickable = job
                if not safe_click(clickable):
                    try:
                        clickable.click()
                    except Exception:
                        logging.warning(f"Could not open job {job_id}; recording and skipping")
                        status = "Could not open job detail"
                        sheet.append([str(job_id), title, company, salary_text, job_link, status])
                        wb.save(EXCEL_FILE)
                        existing_job_ids.add(str(job_id))
                        continue

                time.sleep(1)
                handles = driver.window_handles
                if len(handles) > 1:
                    driver.switch_to.window(handles[-1])
                time.sleep(1)
            except Exception as e:
                logging.error(f"Error opening job detail for {job_id}: {e}", exc_info=True)
                # ensure we record and skip
                status = f"Open detail error: {e}"
                sheet.append([str(job_id), title, company, salary_text, job_link, status])
                wb.save(EXCEL_FILE)
                existing_job_ids.add(str(job_id))
                # attempt to close tab if opened
                try:
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                except Exception:
                    pass
                continue

            # Find apply button on detail page (buttons or anchors containing 'apply')
            apply_btn = None
            try:
                candidate_btns = driver.find_elements(By.XPATH, "//button|//a")
                for b in candidate_btns:
                    try:
                        text = (b.text or "").strip().lower()
                        if "apply" in text:
                            # choose the first clickable visible button/link that contains 'apply'
                            if b.is_displayed():
                                apply_btn = b
                                break
                    except Exception:
                        continue
            except Exception:
                apply_btn = None

            if not apply_btn:
                status = "No Apply Button"
                sheet.append([str(job_id), title, company, salary_text, job_link, status])
                wb.save(EXCEL_FILE)
                existing_job_ids.add(str(job_id))
                logging.info(f"No apply button on detail for {job_id}")
                # close tab if opened
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                continue

            btn_text = ""
            try:
                btn_text = (apply_btn.text or "").strip().lower()
            except Exception:
                btn_text = ""

            # Skip apply on company site
            if "company site" in btn_text or "apply on company" in btn_text:
                status = "Skipped (Company Site)"
                sheet.append([str(job_id), title, company, salary_text, job_link, status])
                wb.save(EXCEL_FILE)
                existing_job_ids.add(str(job_id))
                logging.info(f"Skipped company-site job {job_id}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                continue

            # Attempt to click apply safely
            clicked = safe_click(apply_btn)
            if not clicked:
                try:
                    apply_btn.click()
                except Exception as e:
                    status = "No Apply Button / Not Clickable"
                    sheet.append([str(job_id), title, company, salary_text, job_link, status])
                    wb.save(EXCEL_FILE)
                    existing_job_ids.add(str(job_id))
                    logging.warning(f"Could not click apply for {job_id}: {e}")
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    continue

            # Wait shortly and check for chatbot drawer
            time.sleep(2)
            try:
                chatbot = driver.find_element(By.CLASS_NAME, "chatbot_DrawerContentWrapper")
                if chatbot and chatbot.is_displayed():
                    status = "Skipped (Chatbot)"
                    sheet.append([str(job_id), title, company, salary_text, job_link, status])
                    wb.save(EXCEL_FILE)
                    existing_job_ids.add(str(job_id))
                    logging.info(f"Chatbot appeared for {job_id}, skipped")
                    # close detail tab and continue
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    continue
            except Exception:
                # no chatbot found; proceed
                pass

            # Determine if applied: look for 'applied' in button or consider success
            try:
                new_btn_text = (apply_btn.text or "").strip().lower()
            except Exception:
                new_btn_text = btn_text

            if "applied" in new_btn_text or "applied" in btn_text:
                status = "Applied Successfully"
            else:
                # assume applied successfully if click had no exception
                status = "Applied Successfully"

            # Record and increment only for successful application
            sheet.append([str(job_id), title, company, salary_text, job_link, status])
            wb.save(EXCEL_FILE)
            existing_job_ids.add(str(job_id))
            applied_count += 1
            logging.info(f"Applied to job {job_id} — total applied {applied_count}")

            # close detail tab and return to results
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
                pass

            # small human-like delay
            time.sleep(1.5)

        # finished page
        if applied_count >= MAX_APPLY:
            logging.info(f"Reached target applied_count {applied_count}. Ending.")
            break

        # Try to go to next page (robust selectors)
        logging.info("Attempting to go to next page")
        next_clicked = False
        next_selectors = [
            "//a[contains(text(),'Next')]",
            "//a[@title='Next']",
            "//a[contains(@class,'fright') and contains(., 'Next')]",
            "//a[contains(@class,'np') and contains(., 'Next')]",
            "//a[@rel='next']",
            "//button[contains(., 'Next')]",
            "//a[contains(@class,'srp-pagination-next')]",
            "//a[contains(@aria-label,'Next')]",
        ]
        for sel in next_selectors:
            try:
                elm = driver.find_element(By.XPATH, sel)
                cls = (elm.get_attribute("class") or "").lower()
                if "disabled" in cls:
                    continue
                if safe_click(elm):
                    next_clicked = True
                    page_num += 1
                    time.sleep(4)
                    break
                else:
                    try:
                        elm.click()
                        next_clicked = True
                        page_num += 1
                        time.sleep(4)
                        break
                    except Exception:
                        continue
            except Exception:
                continue

        if not next_clicked:
            logging.info("Next page not found or not clickable; ending pagination.")
            break

    # End main while
    logging.info(f"Completed. Total applied: {applied_count}")
    try:
        wb.save(EXCEL_FILE)
    except Exception:
        logging.warning("Failed to save Excel at final step.")
    driver.quit()
    print(f"Done. Applied {applied_count} jobs. Excel: {EXCEL_FILE}")

except Exception as fatal:
    logging.exception("Fatal error during script execution")
    print(f"Fatal error: {fatal}. See naukri_log.txt and saved screenshots (if any).")
    try:
        driver.save_screenshot("fatal_error.png")
    except Exception:
        pass
    try:
        wb.save(EXCEL_FILE)
    except Exception:
        logging.warning("Could not save Excel in exception handler")
finally:
    try:
        if driver:
            driver.quit()
    except Exception:
        pass
    logging.info("Script finished (final).")
