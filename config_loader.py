import yaml
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "candidate-profile.yaml")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def should_apply(job_title, job_location, platform):
    config = load_config()
    if not config:
        return True
    
    # Geography check
    geo_config = config.get("targeting", {}).get("geography", {})
    if geo_config.get("reject_if_outside_ksa"):
        allowed_cities = geo_config.get("cities", [])
        is_ksa = any(term.lower() in job_location.lower() for term in geo_config.get("allowed", []))
        is_city = any(city.lower() in job_location.lower() for city in allowed_cities)
        if not (is_ksa or is_city):
            return False, "outside_ksa"

    # Seniority check
    seniority_config = config.get("targeting", {}).get("seniority", {})
    reject_keywords = seniority_config.get("reject_title_keywords", [])
    if any(kw.lower() in job_title.lower() for kw in reject_keywords):
        return False, "senior_role"

    # Platform check
    portal_config = config.get("targeting", {}).get("portals", {})
    if platform.lower() in [p.lower() for p in portal_config.get("flag_for_manual_review", [])]:
        return False, "manual_review_platform"

    return True, "ok"
