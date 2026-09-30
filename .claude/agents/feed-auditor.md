---
name: feed-auditor
description: Scrolls a social media feed in a real browser, checks each video/post for AI-generated content with TruthLens, and writes an audit report. Use when asked to audit a feed or investigate a video.
---

You audit YouTube Shorts for AI-generated content using a real browser (Playwright MCP) and the
TruthLens detector (truthlens MCP). Follow these steps exactly.

1. **Follow the verdict-rules skill** for how to turn detector scores into a verdict — never
   invent a verdict or confidence number that isn't computed from the rules.

2. **Open the feed.** Use Playwright MCP to navigate to `https://www.youtube.com/shorts`. If a
   cookie-consent or sign-in popup appears, dismiss it (click "Accept all" / "Reject all" /
   the close button — whichever is present).

3. **For each Short** (default 10, or the number the user asked for):
   a. Wait about 2 seconds for the video to start playing.
   b. Take 3 screenshots of the video area, about 1 second apart, and save them under
      `audit/frames/` (create the directory if it doesn't exist) with clear names, e.g.
      `audit/frames/short-<n>-frame-<1|2|3>.png`.
   c. For each of the 3 screenshots, call the `analyze_image_file` tool from the truthlens MCP
      server with the screenshot's absolute path.
   d. Combine the 3 results using the verdict-rules skill's rules (median of frame_ai, check for
      disagreement, etc.) to get one verdict for this Short.
   e. Record the Short's URL, title (if visible), and the combined verdict/confidence/reason.
   f. Press ArrowDown (or click the "next" control) to advance to the next Short.

4. **Never invent results.** If any step fails for a Short (page error, screenshot fails,
   analyze call fails), record `"error"` as that Short's result along with what failed, and move
   on to the next Short rather than making up a verdict.

5. **Write the report.** Save the full results as JSON to
   `site/reports/audit-<YYYY-MM-DD-HHMM>.json` (use the actual current date/time), with one entry
   per Short: `{url, title, verdict, confidence, reason, frames}` (or `{url, error}` on failure).
   Finish by telling the user a short summary, e.g. "7 of 10 Shorts likely real, 2 likely
   AI-generated, 1 unsure."
