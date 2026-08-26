# Pilot Onboarding — Personal Health Steward (Preclinical)

**Read this whole page first.** This is preclinical software: it is not a
medical service, no clinician monitors your record, and nothing in it is a
diagnosis. If you ever feel this is an emergency, contact local emergency
services directly — do not wait for the app.

## What you need

- One Android or iOS device (the pilot phone).
- A computer or home server to run the relay (any machine with Docker that
  stays on during the pilot).
- The pilot invite message with your **relay address** and **access token**
  (sent separately; treat the token like a password).

## Step 1 — Start the relay (one time, ~10 minutes)

On the relay machine:

```bash
git clone <private repo URL> ai-doctor && cd ai-doctor/deployment
# Edit docker-compose.yml first: replace the two "change-this-*-token"
# values with long random strings, and the push mailto if you enable push.
docker compose up -d
curl http://127.0.0.1:8080/health   # must return {"status":"ok"}
```

The relay stores only encrypted envelopes — it cannot read your record.
Its port is internal to the Docker network by default; expose it only over
a tunnel or VPN you control (e.g. Tailscale). Do not port-forward it raw
to the internet.

## Step 2 — Install the PWA on the pilot phone

1. Open the PWA URL provided in the invite (served by the `pwa` container,
   or any static host of `apps/pwa/dist`).
2. Use the browser's "Add to Home Screen" so it installs as an app and
   works offline.
3. On first launch choose **မြန်မာ** or **English**, enter your age, and
   create the encrypted record when asked.

## Step 3 — Write down the recovery kit

The app shows a one-time recovery code at creation. **Write it on paper**
and keep it with important documents. There is no password reset: without
the recovery code, the encrypted record cannot be opened again. This is by
design — nobody else can read your record either.

## Step 4 — Connect sync (optional but recommended)

In Privacy settings, enter the relay address (`https://…`) and your access
token from the invite. Tap **Sync encrypted events**. Data leaves the
phone only as ciphertext.

## Daily use

- **New concern:** describe a symptom in your own words.
- If the app locks into an emergency screen, it has matched a red-flag
  rule — seek urgent care now; the lock cannot be dismissed by the app.
- Measurements tab records blood pressure / glucose against home-vital
  rules; the Possibility map organizes questions for a real clinician and
  never names diagnoses.

## During the pilot, please note

- Any emergency-screen lock: was it appropriate? (This validates CS-01
  red-flag rules.)
- Anything on screen that felt wrong in Burmese or English (HF-01 wording
  review uses these notes).
- Any crash, stuck sync, or confusing screen — screenshot helps.

Send notes weekly to the contact below. Do not put real diagnoses,
names, or ID numbers in feedback notes — screenshots should show test
data only.

## Stop words

- Export everything: **Privacy panel → export** downloads your encrypted
  event stack as a file you keep.
- Leave the pilot: stop using the app; ask the relay operator to hard-delete
  your server-side data (relay exposes confirmed delete) and revoke your
  device from `/v1/devices` if desired. Local deletion = uninstalling after
  noting the recovery kit is no longer needed.

---
Contact: Min Thant Htoo <minthanthtoo.cs@gmail.com>
