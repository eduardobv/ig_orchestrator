from ig_orchestrator.gui.i18n import locale_keys, load_language, t


def test_locale_files_have_the_same_keys() -> None:
    assert locale_keys("es") == locale_keys("en")
    assert "menu.file.new" in locale_keys("es")


def test_load_language_formats_values() -> None:
    load_language("en")
    assert "Instagram Orchestrator" in t("app.about", version="2.0.0")
    load_language("es")
    assert t("mode.new") == "Nuevo lote"


def test_batch_count_locale_formats_total_and_filtered() -> None:
    load_language("es")
    assert t("label.batch_count", count=3) == "Cuentas: 3"
    assert t("label.batch_count_filtered", visible=1, count=12) == "Cuentas: 1 / 12"
    load_language("en")
    assert t("label.batch_count", count=3) == "Accounts: 3"
    assert t("label.batch_count_filtered", visible=1, count=12) == "Accounts: 1 / 12"
    load_language("es")
