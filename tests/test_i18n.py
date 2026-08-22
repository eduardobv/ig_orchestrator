from ig_orchestrator.gui.i18n import locale_keys, load_language, t


def test_locale_files_have_the_same_keys() -> None:
    assert locale_keys("es") == locale_keys("en")
    assert "menu.file.new" in locale_keys("es")


def test_load_language_formats_values() -> None:
    load_language("en")
    assert "Instagram Orchestrator" in t("app.about", version="2.0.0")
    load_language("es")
    assert t("mode.new") == "Nuevo lote"
