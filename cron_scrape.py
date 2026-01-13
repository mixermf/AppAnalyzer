import os

from pipeline import run_cron_refresh


def main() -> None:
    app_ids_raw = os.getenv("PORTFOLIO_APP_IDS", "")
    app_ids = [x.strip() for x in app_ids_raw.split(",") if x.strip()]
    if not app_ids:
        raise RuntimeError("PORTFOLIO_APP_IDS is empty. Provide comma-separated app ids")

    lang = os.getenv("SCRAPE_LANG", "en")
    country = os.getenv("SCRAPE_COUNTRY", "us")

    for app_id in app_ids:
        try:
            r = run_cron_refresh(app_id=app_id, lang=lang, country=country)
            print(r)
        except Exception as e:  # noqa: BLE001
            print({"app_id": app_id, "status": "error", "error": str(e)})


if __name__ == "__main__":
    main()
