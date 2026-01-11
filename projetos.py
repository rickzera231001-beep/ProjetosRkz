import os
import yaml
from typing import List, Dict, Any

from rpa_scraper import scrape_stats, scrape_odds
from ai_eval import evaluate_matches


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    # Prefer local config when present (config.local.yaml), fallback to config.yaml
    cfg_path = "config.local.yaml" if os.path.exists(
        "config.local.yaml") else "config.yaml"
    cfg = load_config(cfg_path)
    sites = cfg.get("sites", [])
    collected: List[Dict[str, Any]] = []

    for s in sites:
        name = s.get("name")
        url = s.get("url")
        stats_sel = s.get("stats_selectors") or {}
        odds_sel = s.get("odds_selectors") or {}
        try:
            if stats_sel:
                stats = scrape_stats(url, stats_sel)
                stats["source_name"] = name
                stats["source_url"] = url
                collected.append(stats)
            if odds_sel:
                odds = scrape_odds(url, odds_sel)
                odds["source_name"] = name
                odds["source_url"] = url
                collected.append(odds)
        except Exception as e:
            print(f"Erro scraping {name} ({url}): {e}")

    use_openai = cfg.get("openai", {}).get("use_openai", True)
    api_key = cfg.get("openai", {}).get(
        "api_key") or os.getenv("OPENAI_API_KEY")

    results = evaluate_matches(
        collected, use_openai=use_openai, openai_api_key=api_key)

    print("\n--- Recomendações / Scores ---\n")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
