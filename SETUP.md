# Setup Guide — Browser Only (no computer install, no Terminal)

This guide gets you a morning brief **without downloading anything or using a
Terminal**. Everything happens on the GitHub website by clicking buttons and
pasting keys into a settings page.

**What you'll end up with:** every morning at **7:00 AM Malaysia time**, a robot
on GitHub generates your brief. Depending on how far you go:

- **Part A (30 min):** the brief is generated and you can **download and read it**
  from GitHub. This is the minimum.
- **Part B (+10 min):** the brief is also **saved into your Notion** every morning.
- **Part C (later, fiddly):** the brief is also **emailed to you**, and can read
  your Gmail + Calendar.

Do the parts in order. You can stop after any part — each one works on its own.

---

## Words you'll see (quick glossary)

- **Repository ("repo"):** the online folder holding this project, on GitHub.
- **Branch:** a working copy of the code. Yours is called
  `claude/morning-briefing-system-pqlm2u`. The "live" one is called **main**.
- **Pull request (PR):** a request to copy one branch's work into another. You
  approve it with a **Merge** button.
- **GitHub Actions:** the free robot that runs the code on a timer.
- **Secret:** a password/key you paste into GitHub's settings. GitHub locks it
  away so nobody (not even you) can read it back later.
- **Artifact:** a file the robot produces on each run, that you can download.

---

## PART A — Get it running (30 min)

### A1. Make the code "live" (merge it into main)

The robot only runs code on the **main** branch, so we copy the work over.

1. Go to your repository on GitHub (`josephananda2-create/dailys`).
2. You'll likely see a yellow banner: **"claude/morning-briefing-system-pqlm2u
   had recent pushes — Compare & pull request."** Click that green button.
   - *(No banner? Click the **Pull requests** tab → **New pull request** → set
     "base: main" and "compare: claude/morning-briefing-system-pqlm2u".)*
3. Click **Create pull request**.
4. On the next screen, click **Merge pull request**, then **Confirm merge**.
5. Done — the code is now on **main**. (You can ignore/delete the side branch.)

### A2. Get your Anthropic key (this is the AI that writes the brief)

1. Go to <https://console.anthropic.com>.
2. Sign up / log in. Add a payment method under **Billing** (a daily brief costs
   roughly a few US cents per day).
3. Left menu → **API Keys** → **Create Key**. Name it "morning brief".
4. **Copy the key now** (a long string starting `sk-ant-...`). You won't be able
   to see it again — if you lose it, just make a new one.

### A3. Paste the key into GitHub's secret settings

1. In your repository, click the **Settings** tab (top right).
2. Left menu → **Secrets and variables** → **Actions**.
3. Click **New repository secret**.
4. **Name:** `ANTHROPIC_API_KEY`  (type it exactly, all capitals).
   **Secret:** paste your `sk-ant-...` key.
5. Click **Add secret**. You'll see `ANTHROPIC_API_KEY` listed. 

### A4. Test it now (don't wait until 7 AM)

1. Click the **Actions** tab (top of the repo).
2. If asked to enable workflows, click **"I understand my workflows, go ahead
   and enable them."**
3. In the left list, click **Daily Morning Brief**.
4. On the right, click **Run workflow** → **Run workflow** (green button).
5. Wait ~1–2 minutes. Refresh. A run appears with a spinning circle, then a
   green tick ✓ when done.

### A5. Read your brief

1. Click into that finished run.
2. Scroll to the bottom to the **Artifacts** box → click **morning-brief** to
   download it.
3. Unzip it and open the `.md` file — that's your brief. 

**You now have a working system.** At 7:00 AM Malaysia time it will run on its
own and produce this file every day. To *also* get it in Notion or email,
continue below.

---

## PART B — Save it to Notion every morning (+10 min)

### B1. Create a Notion integration

1. Go to <https://www.notion.so/my-integrations> → **New integration**.
2. Name it "Morning Brief", pick your workspace, submit.
3. Copy the **Internal Integration Secret** (starts `secret_` or `ntn_`).

### B2. Make a home page and share it

1. In Notion, create a new blank page called e.g. **"Morning Brief"**.
2. On that page, click the **•••** menu (top right) → **Connections** (or
   "Add connections") → choose your **Morning Brief** integration.
3. Copy the page's ID: open the page, look at its web address. The ID is the
   32-character jumble at the end (letters and numbers, ignore any `?...` part).
   Example: in `notion.so/My-Page-1a2b3c4d5e6f...`, the ID is the `1a2b3c...` bit.

### B3. Add two more secrets in GitHub

Same as step A3 (**Settings → Secrets and variables → Actions → New repository
secret**), add these two:

| Name | Secret value |
|---|---|
| `NOTION_API_KEY` | the integration secret from B1 |
| `NOTION_PARENT_PAGE_ID` | the 32-character page ID from B2 |

### B4. Test

Do step A4 again (**Actions → Daily Morning Brief → Run workflow**). After the
green tick, check Notion — a new **"Morning Brief Archive"** database appears
under your page, with today's brief inside. From now on it saves there every
morning.

---

## PART C — Email it to you + read Gmail & Calendar (later; the fiddly one)

This unlocks the email delivery and the "My day ahead" section. It's the most
involved part because Google requires several screens. It's still all in the
browser. Tackle it when you have a spare 30 minutes — the brief already works
without it.

### C1. Turn on the Google APIs

1. Go to <https://console.cloud.google.com>.
2. Top bar → **Select a project** → **New Project** → name it "Morning Brief" →
   **Create**, then make sure it's selected.
3. Search bar → "**Gmail API**" → **Enable**.
4. Search bar → "**Google Calendar API**" → **Enable**.

### C2. Set up the consent screen

1. Left menu → **APIs & Services** → **OAuth consent screen**.
2. Choose **External** → **Create**.
3. Fill app name "Morning Brief" and your email where required, **Save and
   Continue** through the steps.
4. On **Test users**, click **Add users** and add your own Gmail address
   (`josephananda2@gmail.com`). Save.

### C3. Create the login credentials

1. Left menu → **Credentials** → **Create Credentials** → **OAuth client ID**.
2. Application type: **Web application**. Name: "Morning Brief".
3. Under **Authorised redirect URIs**, click **Add URI** and paste:
   `https://developers.google.com/oauthplayground`
4. **Create.** Copy the **Client ID** and **Client Secret** it shows you.

### C4. Get the "refresh token" (browser tool)

1. Go to <https://developers.google.com/oauthplayground>.
2. Click the **gear icon** (top right) → tick **"Use your own OAuth
   credentials"** → paste your Client ID and Client Secret → close.
3. On the left, in the "Input your own scopes" box, paste these three (separated
   by spaces):
   ```
   https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/calendar.readonly
   ```
4. Click **Authorize APIs** → sign in with your Google account → allow.
   *(If it warns the app is unverified, click Advanced → "Go to Morning Brief".)*
5. Back on the playground, click **Exchange authorization code for tokens**.
6. Copy the **Refresh token** value (a long string starting `1//...`).

### C5. Add the Google secrets in GitHub

Add these (Settings → Secrets and variables → Actions → New repository secret):

| Name | Secret value |
|---|---|
| `GOOGLE_CLIENT_ID` | Client ID from C3 |
| `GOOGLE_CLIENT_SECRET` | Client Secret from C3 |
| `GOOGLE_REFRESH_TOKEN` | Refresh token from C4 |
| `BRIEF_RECIPIENT` | `josephananda2@gmail.com` |

### C6. Test

Run the workflow again (step A4). Within a couple of minutes, the brief should
land in your **email inbox**, and the "My day ahead" section will start using
your real calendar.

---

## After setup — where & when your brief arrives

Once you've done the parts you want, **every morning at 7:00 AM Malaysia time**
the robot runs automatically and your brief appears in:

- **GitHub** — as a downloadable file on the run (always).
- **Notion** — as a new archive page (if you did Part B).
- **Your email inbox** (if you did Part C).

You never press anything. Your computer can be off.

---

## Making it yours (anytime, all in the browser)

Your sources and clients live in three text files you can edit directly on
GitHub — click the file, click the **pencil ✏️ icon**, edit, then **Commit
changes**:

- `config/sources.yaml` — add/remove/pause news sources. (Some are left as
  `ADD_..._HERE` placeholders — fill in the real feed links when you find them.)
- `config/categories.yaml` — put your **real client names** in the `watchlist:`
  section so their brand mentions get flagged.
- `config/scoring.yaml` — change how items are ranked.

No other changes needed — the system re-reads these every morning.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| A run has a red ✗ | Click into it, read the red step. Usually a mistyped secret name — they must match exactly (all caps). |
| No email arrived | You need Part C. Also check the secret name is exactly `BRIEF_RECIPIENT`. |
| Nothing in Notion | Check you **shared the page** with the integration (step B2) and the page ID is correct. |
| Brief looks thin / "extractive mode" | The `ANTHROPIC_API_KEY` secret is missing or wrong — redo A2–A3. |
| "Workflows aren't running on schedule" | Open the **Actions** tab once and enable workflows; scheduled runs pause if the repo is untouched for 60 days. |
| Want to run it right now | Actions tab → Daily Morning Brief → **Run workflow**. |
