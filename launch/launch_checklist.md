# Launch checklist — do these in order

## Day before launch

- [ ] `pip install agentsdk-py` in a clean venv — verify it works end to end
- [ ] Docs site loads at https://vishwa0198.github.io/agentsdk
- [ ] All GitHub community files committed and pushed (.github/, CONTRIBUTING.md, SECURITY.md)
- [ ] README badges updated (PyPI version, Python, License, Docs)
- [ ] Record a 60-second screen recording:
      `scaffold-agent new` → `agent.run()` → output in terminal
      (embed in Product Hunt gallery + pin to Twitter)
- [ ] Create the four Product Hunt gallery images (see product_hunt_post.md)
- [ ] Write the HN post in a text file so you can paste it quickly
- [ ] Schedule the Twitter thread in a draft (don't post yet)

---

## Launch day — post at 9am US Eastern (7:30pm IST)

Post in this order:

- [ ] **1. Post Show HN** — paste from hn_post.md
      URL: https://news.ycombinator.com/submit
- [ ] **2. Submit to Product Hunt** — paste from product_hunt_post.md
      URL: https://www.producthunt.com/posts/new
- [ ] **3. Post Twitter thread** — fire off tweets 1–7 from twitter_thread.md
- [ ] **4. Publish blog post** on dev.to (https://dev.to/new)
- [ ] **5. Cross-post blog** to Hashnode (https://hashnode.com/post/new)
- [ ] **6. Share on LinkedIn** — paste blog intro + link
- [ ] **7. Post in r/Python**
      Title: "Show r/Python: agentsdk — open-source Python AI agent SDK (ReAct, @tool, multi-agent)"
      Check r/Python rules — self-promo usually allowed on weekends
- [ ] **8. Post in r/MachineLearning**
      Use the "Project" flair. Keep it technical.
- [ ] **9. Share in Discord servers**
      - Hugging Face (#show-your-work)
      - LangChain Discord (if there's a community channel)
      - AI Engineers Discord
      - Python Discord (#projects)

---

## First 2 hours after launch

- [ ] Monitor HN comments tab — reply to every comment within 2 hours
      (HN ranks comments partly by response time from the author)
- [ ] Monitor Product Hunt notifications — upvote thoughtful comments
- [ ] Check for any error reports in GitHub Issues — fix critical bugs same day
- [ ] Pin the "introduce yourself" Discussion on GitHub

---

## After launch (ongoing)

- [ ] Reply to every Product Hunt comment same day
- [ ] Check PyPI downloads after 24h: https://pypi.org/project/agentsdk-py/#history
- [ ] Add Plausible Analytics (free tier) to docs site for visitor tracking
- [ ] If HN post gets 50+ points, write a follow-up comment summarising key feedback
- [ ] Tag any contributors or supporters in a thank-you tweet

---

## Metrics to track (set up a spreadsheet with these columns)

| Metric | Day 1 | Day 3 | Day 7 | Day 30 |
|--------|-------|-------|-------|--------|
| PyPI downloads | | | | |
| GitHub stars | | | | |
| HN points | | | | |
| HN comments | | | | |
| Product Hunt upvotes | | | | |
| Docs site visits | | | | |
| GitHub forks | | | | |

Check PyPI stats at: https://pypistats.org/packages/agentsdk-py

---

## Final pre-launch verification

```bash
# Clean environment test
python -m venv /tmp/agentsdk_test
/tmp/agentsdk_test/bin/pip install agentsdk-py==0.2.0
/tmp/agentsdk_test/bin/python -c "import agentsdk; print(agentsdk.__version__)"
# Expected: 0.2.0

# Docs site
# Open https://vishwa0198.github.io/agentsdk in a browser

# GitHub repo
# Confirm it is public at https://github.com/vishwa0198/agentsdk
# Confirm README, CONTRIBUTING.md, SECURITY.md, .github/ are all present
```
