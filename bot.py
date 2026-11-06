name: gridiron-bot

on:
  schedule:
    - cron: "*/10 * * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: gridiron-bot
  cancel-in-progress: false

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - run: pip install -r requirements.txt

      - name: Run bot
        run: python bot.py
        env:
          FB_PAGE_ID: ${{ secrets.FB_PAGE_ID }}
          FB_PAGE_TOKEN: ${{ secrets.FB_PAGE_TOKEN }}

      - name: Save state (so nothing is posted twice)
        if: always()
        run: |
          git config user.name "gridiron-bot"
          git config user.email "gridiron-bot@users.noreply.github.com"
          git add state.json 2>/dev/null || true
          git diff --cached --quiet || (git commit -m "update state" && git push)
