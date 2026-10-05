"""JPBL PowerPro Importer GUI entry point."""


def main() -> None:
    try:
        from app.main_window import run
    except ImportError as error:
        raise SystemExit(
            "GUI依存関係がありません。\n"
            "`python -m pip install -r requirements.txt` を実行してください。"
        ) from error
    run()


if __name__ == "__main__":
    main()
