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
# Prefer env vars for secrets in CI; fall back to hard-coded values for local tests
NAUKRI_EMAIL = os.getenv("NAUKRI_EMAIL", "ameypatankar333@gmail.com")
NAUKRI_PASSWORD = os.getenv("NAUKRI_PASSWORD", "9773051915")
SKILLS = os.getenv("SKILLS", "Java and Spring Boot And React")
EXPERIENCE = os.getenv("EXPERIENCE", "11")  # years
EXCEL_FILE = os.getenv("EXCEL_FILE", "applied_jobs.xlsx")
MIN_EXPECTED_SALARY = float(os.getenv("MIN_EXPECTED_SALARY", "25"))  # LPA
MAX_APPLY = int(os.getenv("MAX_APPLY", "50"))  # Number of successful applications to reach
CHROME_DRIVER_PATH = os.getenv("CHROME_DRIVER_PATH", "")  # optional path
HEADLESS = True  # For GitHub Actions / automation, keep True

LOGIN_URL = "https://www.naukri.com/nlogin/login"
SEARCH_URL = "https://www.naukri.com/jobs-in-india"

# ---------------- LOGGING ----------------
logging.basicConfig(
    filename="naukri_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.info("Script started")
print("Script started (headless). See naukri_log.txt for details.")

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
    if row and row[0] is not None:
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
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

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
            time.sleep(0.15)
        actions.move_to_element(element).pause(0.12).click().perform()
        return True
    except (ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException, Exception) as exc:
        logging.warning(f"safe_click failed: {exc}")
        return False

def parse_max_salary(salary_text):
    """Try to extract a numeric maximum salary in LPA from salary_text. Returns float or None."""
    if not salary_text:
        return None
    s = salary_text.lower()
    if "not disclose" in s:
        return None
    # normalize
    s = s.replace("lacs pa", "lpa").replace("lacs", "lpa").replace("per annum", "").replace("p.a.", "").replace("pa", "")
    nums = re.findall(r"[\d\.]+", s)
    if not nums:
        return None
    try:
        val = float(nums[-1])
        # if text contains 'lpa' or 'lac', return as is
        if "lpa" in s or "lac" in s:
            return val
        # otherwise return the number as-is (best effort)
        return val
    except Exception:
        return None

def save_record(job_id, title, company, salary_text, job_link, status):
    """Append a row to Excel and save immediately, and mark job id as processed."""
    try:
        sheet.append([str(job_id), title, company, salary_text, job_link, status])
        wb.save(EXCEL_FILE)
    except Exception as e:
        logging.error(f"Failed to write to Excel: {e}")
    existing_job_ids.add(str(job_id))

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
        # focus search container
        search_bar_container = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "nI-gNb-sb__main")))
        safe_click(search_bar_container)
        search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Enter keyword / designation / companies']")))
        search_box.clear()
        search_box.send_keys(SKILLS)
        # experience dropdown
        exp_dropdown = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='dropdownMainContainer']")))
        safe_click(exp_dropdown)
        exp_option = wait.until(EC.element_to_be_clickable((By.XPATH, f"//li[@title='{EXPERIENCE} years']")))
        safe_click(exp_option)
        # search button
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
        try:
            jobs = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class,'srp-jobtuple-wrapper') or contains(@class,'jobTuple')]")))
        except TimeoutException:
            logging.info("No job cards found on this page. Ending loop.")
            break

        if not jobs:
            logging.info("Job list empty; ending.")
            break

        # iterate using index to avoid stale references
        total = len(jobs)
        idx = 0
        while idx < total and applied_count < MAX_APPLY:
            # re-fetch job list each iteration to reduce stale refs
            try:
                jobs = driver.find_elements(By.XPATH, "//div[contains(@class,'srp-jobtuple-wrapper') or contains(@class,'jobTuple')]")
                job = jobs[idx]
            except Exception:
                idx += 1
                continue
            idx += 1

            try:
                job_id = job.get_attribute("data-job-id")
            except StaleElementReferenceException:
                continue

            if not job_id:
                continue

            if str(job_id) in existing_job_ids:
                # skip duplicates (do not increment)
                logging.debug(f"Skipping duplicate job_id {job_id}")
                continue

            # extract job details safely
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

            logging.info(f"Found job: {job_id} | {title} | {company} | {salary_text}")

            # If card indicates Already Applied -> record and skip (do not increment)
            try:
                applied_tag = job.find_element(By.XPATH, ".//span[contains(text(),'Applied')]")
                if applied_tag.is_displayed():
                    status = "Already Applied"
                    save_record(job_id, title, company, salary_text, job_link, status)
                    logging.info(f"Card shows Already Applied for {job_id} — recorded and skipped")
                    continue
            except Exception:
                pass

            # Salary filter
            max_sal = parse_max_salary(salary_text)
            if (max_sal is not None) and (max_sal < MIN_EXPECTED_SALARY):
                status = "Skipped (Low Salary)"
                save_record(job_id, title, company, salary_text, job_link, status)
                logging.info(f"Skipped low salary job {job_id}: {salary_text}")
                continue

            # Open job details (click title); it may open in a new tab
            try:
                clickable = title_elem
                if not safe_click(clickable):
                    try:
                        clickable.click()
                    except Exception:
                        status = "Could not open job detail"
                        save_record(job_id, title, company, salary_text, job_link, status)
                        continue

                time.sleep(1)
                handles = driver.window_handles
                if len(handles) > 1:
                    driver.switch_to.window(handles[-1])
                time.sleep(1)
            except Exception as e:
                logging.error(f"Error opening job detail for {job_id}: {e}", exc_info=True)
                status = f"Open detail error: {e}"
                save_record(job_id, title, company, salary_text, job_link, status)
                # try to close any extra tab and continue
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
                candidate = driver.find_elements(By.XPATH, "//button|//a")
                for b in candidate:
                    try:
                        txt = (b.text or "").strip().lower()
                        if "apply" in txt:
                            if b.is_displayed() and b.is_enabled():
                                apply_btn = b
                                break
                    except Exception:
                        continue
            except Exception:
                apply_btn = None

            if not apply_btn:
                status = "No Apply Button"
                save_record(job_id, title, company, salary_text, job_link, status)
                logging.info(f"No apply button on detail for {job_id}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                continue

            btn_text = (apply_btn.text or "").strip().lower()

            # If button indicates 'Apply on company site' -> skip and record (do not increment)
            if "company site" in btn_text or "apply on company" in btn_text:
                status = "Skipped (Company Site)"
                save_record(job_id, title, company, salary_text, job_link, status)
                logging.info(f"Skipped company-site job {job_id}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                continue

            # If button already says "Applied" -> record Already Applied and skip (do not increment)
            if "applied" in btn_text:
                status = "Already Applied"
                save_record(job_id, title, company, salary_text, job_link, status)
                logging.info(f"Detail shows Already Applied for {job_id}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                continue

            # else btn_text likely 'apply' -> click it to apply
            clicked = safe_click(apply_btn)
            if not clicked:
                try:
                    apply_btn.click()
                except Exception as e:
                    status = "No Apply Button / Not Clickable"
                    save_record(job_id, title, company, salary_text, job_link, status)
                    logging.warning(f"Could not click apply for {job_id}: {e}")
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    continue

            # After clicking, wait a bit and check for chatbot drawer
            time.sleep(2)
            try:
                chatbot = driver.find_element(By.CLASS_NAME, "chatbot_DrawerContentWrapper")
                if chatbot and chatbot.is_displayed():
                    status = "Skipped (Chatbot)"
                    save_record(job_id, title, company, salary_text, job_link, status)
                    logging.info(f"Chatbot appeared for {job_id}; skipped")
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    continue
            except Exception:
                # no chatbot - proceed
                pass

            # Check if apply succeeded (look for 'Applied' text on page or on button)
            try:
                # attempt to re-find button text
                new_text = ""
                try:
                    new_text = (apply_btn.text or "").strip().lower()
                except Exception:
                    new_text = ""
                if "applied" in new_text:
                    status = "Applied Successfully"
                else:
                    # assume success if no errors and click completed
                    status = "Applied Successfully"
            except Exception:
                status = "Applied (unknown state)"

            # Record success and increment only when Applied Successfully
            save_record(job_id, title, company, salary_text, job_link, status)
            if status == "Applied Successfully":
                applied_count += 1
                logging.info(f"Applied to {job_id} — total applied {applied_count}")
            else:
                logging.info(f"Processed {job_id} with status: {status}")

            # Close detail tab and switch back to results
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                else:
                    # ensure we remain on results page; if navigation happened in same tab, go back
                    try:
                        driver.back()
                    except Exception:
                        pass
            except Exception:
                pass

            time.sleep(1.2)  # small human-like delay

        # Finished iterating page
        if applied_count >= MAX_APPLY:
            logging.info(f"Reached MAX_APPLY ({MAX_APPLY}). Ending.")
            break

        # Try pagination: click Next and continue
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

    # Main loop done
    logging.info(f"Completed. Total applied: {applied_count}")
    try:
        wb.save(EXCEL_FILE)
    except Exception:
        logging.warning("Failed to save Excel at final step.")
    driver.quit()
    print(f"Done. Applied {applied_count} jobs. Excel: {EXCEL_FILE}")

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
        logging.warning("Could not save Excel in exception handler")
finally:
    try:
        if driver:
            driver.quit()
    except Exception:
        pass
    logging.info("Script finished (final).")
