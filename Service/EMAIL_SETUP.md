# LUMAX Email Notification Setup (Gmail)

This guide will help you set up email notifications for LUMAX crash alerts using your Gmail account.

## Overview

LUMAX can send you email alerts when:
- A service crashes
- Critical system errors occur
- Director healing missions complete

The system uses Gmail SMTP with an app password.

## Step 1: Enable 2-Factor Authentication on Gmail

1. Go to your Google Account: https://myaccount.google.com
2. Select **Security** from the left menu
3. Under "Signing in to Google", click **2-Step Verification**
4. Follow the steps to enable it (if not already enabled)

## Step 2: Generate an App Password

1. Go to: https://myaccount.google.com/apppasswords
2. Select **Mail** as the app
3. Select your device (or choose "Other" and type "LUMAX")
4. Click **Generate**
5. Copy the 16-character password (it looks like: `abcd efgh ijkl mnop`)

## Step 3: Configure LUMAX

Edit your `.env` file and update the password:

```env
LUMAX_EMAIL_SMTP_SERVER=smtp.gmail.com
LUMAX_EMAIL_SMTP_PORT=587
LUMAX_EMAIL_SENDER=1um6a77@gmail.com
LUMAX_EMAIL_PASSWORD=abcdefghijklmnop  # Your 16-char app password (no spaces)
LUMAX_EMAIL_RECIPIENT=1um6a77@gmail.com
```

## Step 4: Test the Configuration

1. Restart the LUMAX web service:
   ```powershell
   # If running as Windows Service
   Restart-Service -Name "LumaxService"
   ```

2. Test via the Web UI:
   - Open http://localhost:8080
   - Go to Settings → Email Configuration
   - Click "Send Test Email"

3. Or test via API (PowerShell):
   ```powershell
   curl -X POST http://localhost:8080/api/inbox/send-test-email `
     -H "Cookie: lumax_pw=your-password"
   ```

## Troubleshooting

### Email not sending?

1. Check the `.logs/webui.log` for error messages
2. Verify 2-Factor Authentication is enabled on your Gmail
3. Make sure you're using the App Password, not your regular Gmail password
4. Remove any spaces from the app password (should be 16 continuous characters)

### Want to disable email notifications?

Simply remove or comment out the email lines in `.env`. The system will continue to work and show notifications in the Web UI inbox.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/inbox/email-config` | GET | Get current email configuration |
| `/api/inbox/email-config` | PUT | Update email configuration |
| `/api/inbox/send-test-email` | POST | Send a test email |
| `/api/inbox/notify-crash?report_id={id}` | POST | Send email for specific crash |

## Email Template Preview

Crash alert emails include:
- ⚠️ Warning icon with color-coded severity
- Service name that crashed
- Timestamp of the crash
- Brief summary
- Link to view full details in Web UI