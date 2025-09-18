# Update `naukri_apply.py` Configuration

Please update the following fields in the `naukri_apply.py` file with your details:

| Field | Description | Example / Placeholder |
|-------|-------------|---------------------|
| `NAUKRI_EMAIL` | Your Naukri login email | `"your_email@example.com"` |
| `NAUKRI_PASSWORD` | Your Naukri login password | `"your_password"` |
| `SKILLS` | Skills to search for jobs | `"Java, Spring Boot, React"` |
| `EXPERIENCE` | Your total experience in years | `"11"` |
| `TEXT_VALUE_FOR_BOT` | Message to auto-fill in chatbot | `"I have 11 yrs of experience and expecting 43L CTC"` |

**Important:**  
- The batch will run **every day at 7 PM IST**.  
- Make sure the file is saved after updating the values.

### Manual Run Steps

1. Go to the **Actions** tab in your GitHub repository.  
2. Select the **Naukri Apply Automation** workflow from the list.  
3. Click **Run workflow** → choose the branch you want → click **Run workflow**.  

The workflow will:  

- Launch the script using **headless Chrome**.  
- Log in to Naukri with the credentials set in `naukri_apply.py`.  
- Search and apply for jobs based on the **skills** and **experience** you configured.  
- Fill chatbot prompts automatically using `TEXT_VALUE_FOR_BOT`.  
- Save all applied jobs and statuses to `applied_jobs.xlsx`.  
- Optionally, upload `applied_jobs.xlsx` as an artifact (if configured in workflow).  

Once complete, you can view the workflow logs for success/failure details and download the Excel artifact if uploaded.

