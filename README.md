# Naukri Job Apply Automation

Automate job applications on Naukri.com based on your skills and experience. The workflow will also auto-fill chatbot prompts and save applied jobs to an Excel file.

---

## 1️⃣ Configure GitHub Secrets

To keep credentials secure, store them as **GitHub Secrets** in your repository.

1. Go to your repository → Settings → Secrets and variables → Actions → New repository secret.
2. Add the following secrets:

| Secret Name          | Description                            | Example Value                                   |
|----------------------|----------------------------------------|------------------------------------------------|
| `NAUKRI_EMAIL`       | Your Naukri login email                 | your_email@example.com                          |
| `NAUKRI_PASSWORD`    | Your Naukri login password              | your_password                                   |
| `SKILLS`             | Skills to search for jobs               | Java, Spring Boot, React                        |
| `EXPERIENCE`         | Your total experience in years          | 11                                             |
| `TEXT_VALUE_FOR_BOT` | Message to auto-fill in chatbot         | I have 11 yrs of experience and expecting 43L CTC |

> **Important:** Do not store credentials directly in code.

---

## 2️⃣ Workflow Schedule

- The workflow is scheduled to run **every day at 7 PM IST** automatically.
- It can also be triggered manually from the **Actions** tab.

---

## 3️⃣ Manual Run Steps

1. Go to the **Actions** tab in your GitHub repository.
2. Select the **Naukri Apply Automation** workflow.
3. Click **Run workflow** → choose the branch → click **Run workflow**.

The workflow will:

- Launch the script using headless Chrome.
- Log in to Naukri using the secrets configured above.
- Search and apply for jobs based on skills and experience.
- Auto-fill chatbot prompts using `TEXT_VALUE_FOR_BOT`.
- Save applied jobs and statuses to `applied_jobs.xlsx`.
- Optionally, upload `applied_jobs.xlsx` as an artifact for download.

---

## 4️⃣ Output

- Applied jobs and statuses are saved in `applied_jobs.xlsx`.
- Logs are saved in `naukri_log.txt`.
- You can view workflow logs in the **Actions** tab for success/failure details.
