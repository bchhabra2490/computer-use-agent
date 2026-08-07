---
name: hn-comments
description: >-
  Finds comments on the user's Hacker News submissions. Use when the user asks
  about HN feedback, replies on their posts, or latest comments on their
  stories.
---

# Hacker News — my comments / replies

## Steps

1. Follow **open-app** / **web-search** as needed to open Chrome.
2. Go to `https://news.ycombinator.com`.
3. If the username is unknown, call `ask_user` for their HN username.
4. Open their profile (`https://news.ycombinator.com/user?id=USERNAME`) or use
   the site search / threads link from the header when logged in.
5. Open their submissions, then open each recent story’s comment thread and
   look for replies addressed to them or nested under their comments.
6. Summarize findings for the user (story title, commenter, snippet). Use
   `ask_user` if they want you to open a specific thread or draft a reply.

## Tips

- Prefer the official HN UI over third-party mirrors.
- Do not post comments unless the user clearly asks you to.
