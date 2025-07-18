import csv
import time
import openai
from serpapi import GoogleSearch
from playwright.sync_api import sync_playwright
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os
import base64
from email.mime.text import MIMEText

# === SETUP ===
openai.api_key = "MY_API_KEY"
SERPAPI_KEY = "MY_SERPAPI_KEY"
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# === STEP 1: Fetch Businesses from SerpAPI ===
def fetch_lawncare_businesses():
    print("[*] Fetching lawn care businesses from SerpAPI...")
    params = {
        "engine": "google_maps",
        "q": "lawn care services",
        "type": "search",
        "location": "Denver, Colorado, United States",
        "api_key": SERPAPI_KEY
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    return results.get("local_results", [])

# === STEP 2: Scrape Website for Email and Text ===
def extract_email_and_text(website):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(website, timeout=15000)
            page.wait_for_selector("body", timeout=5000)
            text = page.locator("body").inner_text()[:1000]
            emails = page.evaluate("() => document.body.innerText.match(/[\\w.+-]+@[\\w-]+\\.[\\w.-]+/g)")
            email = emails[0] if emails else "Not Found"
        except Exception as e:
            print(f"[!] Failed to extract from {website}: {e}")
            email, text = "Not Found", "Failed to load"
        browser.close()
    return email, text

# === STEP 3: Generate Personalized Email ===
def generate_email(business_name, website_text):
    prompt = f"""
Write a short, friendly cold outreach email to a lawn care company named {business_name}.
Their website says: "{website_text}"

You are introducing a product called Lawn Weeder that automates weed removal.
Keep it useful, conversational, and non-spammy.
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        print(f"[!] OpenAI API failed: {e}")
        return "Error generating message."

# === STEP 4: Gmail API Setup ===
def gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    service = build('gmail', 'v1', credentials=creds)
    return service

# === STEP 5: Send Email ===
def send_email(service, to, subject, message_text):
    message = MIMEText(message_text)
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        sent_message = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return "Sent"
    except Exception as e:
        print(f"[!] Email failed to {to}: {e}")
        return f"Failed: {e}"

# === MAIN WORKFLOW ===
def main():
    service = gmail_service()
    businesses = fetch_lawncare_businesses()
    LIMIT = 10  # max businesses to process

    with open("final_leads.csv", mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Business", "Website", "Phone", "Email", "Message", "Status"])

        for idx, biz in enumerate(businesses):
            if idx >= LIMIT:
                print("[*] Limit reached, stopping.")
                break

            name = biz.get("title")
            website = biz.get("website", "")
            phone = biz.get("phone", "")

            print(f"\n[+] Processing ({idx+1}/{LIMIT}): {name}")
            if website:
                email, site_text = extract_email_and_text(website)
            else:
                email, site_text = "Not Found", "No website found"

            print(f"  - Email found: {email}")
            message = generate_email(name, site_text)
            recipient = email if email != "Not Found" else "moosarayyan2006@gmail.com"
            status = send_email(service, recipient, f"Quick idea for {name}", message)

            print(f"  - Email send status: {status}")

            writer.writerow([name, website, phone, email, message, status])
            time.sleep(5)

if __name__ == "__main__":
    main()
