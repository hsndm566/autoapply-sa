# APPLICATION METHODS (extracted from research sweep)

## Channels (apply through ALL available per job)
1. **Company portal form** (Greenhouse/Lever/Ashby/Workday) — easiest to automate via API + Playwright.
2. **Direct email** to hiring manager / HR — discover via Apollo/Proxycurl or pattern (`first.last@company.com`); send tailored CV + cover letter.
3. **LinkedIn Easy Apply** — Playwright selector map (neonwatty/job-apply-plugin, AkbarDevop/ai-job-agent).
4. **One-click apply** on boards (Wellfound, Dice, etc.).

## Browser automation (required for portals + Easy Apply)
- **Playwright** (Python) is the standard. Selector maps per ATS:
  - Greenhouse: fill text inputs by label, answer custom questions as mini-interviews, upload CV.
  - Lever: similar, fewer custom questions.
  - Ashby: React form, wait for hydration.
  - Workday: worst — heavy JS, often needs manual step (flag + queue).
  - LinkedIn Easy Apply: multi-step wizard, answer "yes/no" + upload.
- **Human-gated submission** (Liam-Frost/AutoApply default): draft + tailor + fill, but pause before final submit for review on high-value roles. For bulk, auto-submit after double-check pass.

## Safety / compliance
- Track every submission (CSV/DB): company, role, channel, timestamp, status.
- Flag manual steps (Workday auth, captcha) → separate review queue.
- Respect ToS: prefer ATS APIs + email; avoid aggressive Indeed/LinkedIn scraping.
- Double-check pass (orchestrator.py) runs before any submit.

## Backend
- Heavy processing on Azure B1S (free tier). Local machine = control terminal only.
- Browser applies need a headless Chromium on the VM (Playwright install) OR the user's local `hermes chat` with `/browser connect` (chat sandbox can't reach local Chrome).
- GitHub Actions handles scraping + drafting + review (free); Azure handles browser submits + 24/7.
