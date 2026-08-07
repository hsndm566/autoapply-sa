#!/usr/bin/env python3
"""personal_brand.py — weekly inbound presence builder (parallel to applying).

Every week:
  1. Pick ONE topic relevant to the client's field where they have something useful to say.
  2. Draft a LinkedIn post/article in the client's VOICE (uses their profile/CV).
  3. Queue it for APPROVAL (never auto-post) -> /skills/personal-brand.md pending section.
  4. Track engagement + post type over time.
  5. After a post spike, capture LinkedIn profile VIEWERS as warm leads.
  6. Draft a connection request to every recruiter/hiring-manager viewer within 48h.

Inbound is cheaper than outbound — build both simultaneously.

API-first: draft via free LLM; approval + posting + viewer-monitoring need the
client's LinkedIn session (human-gated, per operating rules). The agent prepares
everything; the client approves + posts.
"""
import os, re, datetime, json

BASE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.join(BASE, "skills", "personal-brand.md")


def draft_post(name, cv_text, field_topic=None):
    """Draft one LinkedIn post in the client's voice. Returns (topic, post_text)."""
    import orchestrator as O
    topic = field_topic or _pick_topic(cv_text)
    prompt = (
        f"You are {name}. Write a LinkedIn post in THEIR authentic voice (first person, "
        f"confident but not braggy, 120-180 words). Topic: {topic}. They have something "
        f"useful to say from their background. CV:\n{cv_text[:1000]}\n\n"
        f"Hook in line 1. One concrete lesson or observation. End with a soft question to "
        f"invite replies. No hashtag spam (max 3 relevant).")
    post, prov = O.drafter_agent(prompt, cv_text)
    return topic, post, prov


def _pick_topic(cv_text):
    """Pick a relevant topic from the client's field (simple heuristic)."""
    cv = cv_text.lower()
    if "industrial" in cv or "process" in cv:
        return "a process-optimization win from your work that others can copy"
    if "data" in cv or "engineer" in cv:
        return "a data lesson that changed how you work"
    if "sales" in cv:
        return "a sales insight that actually moved numbers"
    return "a hard lesson from your field worth sharing"


def queue_for_approval(name, topic, post):
    """Append post to approval queue in personal-brand.md."""
    with open(BRAND, "a", encoding="utf-8") as f:
        f.write(f"\n## PENDING APPROVAL — {datetime.date.today().isoformat()} ({name})\n")
        f.write(f"**Topic:** {topic}\n\n{post}\n\n")
        f.write(f"_Status: QUEUED — awaiting client approval before posting._\n")
    return True


def track_engagement(post_id, post_type, likes, comments, views):
    """Log engagement per post -> builds the 90-day content pattern."""
    with open(BRAND, "a", encoding="utf-8") as f:
        f.write(f"\n### ENGAGEMENT {datetime.date.today().isoformat()} | post#{post_id} | {post_type}\n")
        f.write(f"- likes: {likes} | comments: {comments} | views: {views}\n")
    return {"post_id": post_id, "type": post_type, "likes": likes,
            "comments": comments, "views": views}


def draft_connection_request(viewer_name, viewer_role):
    """Draft a warm connection request to a recruiter/hiring-manager who viewed
    the profile within 48h of a post spike."""
    return (f"Hi {viewer_name}, thanks for checking out my profile after my post on "
            f"{viewer_role}. I'm open to "
            f"relevant opportunities in this space — happy to connect.")


def run(client_name, cv_text):
    """Weekly run: draft + queue one post. (Engagement tracking + viewer capture
    are fed by the client's LinkedIn session data, logged via track_engagement.)"""
    topic, post, prov = draft_post(client_name, cv_text)
    queue_for_approval(client_name, topic, post)
    return {"topic": topic, "queued": True, "provider": prov}


if __name__ == "__main__":
    cv = "Hasan Adam, Industrial Engineering graduate, Riyadh, process optimization, Six Sigma."
    print(run("Commander", cv))
