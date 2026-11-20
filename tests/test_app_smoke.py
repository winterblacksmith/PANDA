import sqlite3

from streamlit.testing.v1 import AppTest


def test_geotiff_is_available_and_opens_from_dataset_selector():
    app = AppTest.from_file("app.py", default_timeout=30).run()

    assert not app.exception
    assert not any(expander.label == "Raster layers" for expander in app.expander)
    assert not any("FVS stand simulation results" in heading.value for heading in app.subheader)
    assert any("What would you like to explore?" in item.value for item in app.markdown)
    app.toggle(key="show_dataset_details").set_value(True).run()
    assert any("FVS stand simulation results" in heading.value for heading in app.subheader)
    theme_selector = app.sidebar.segmented_control[0]
    assert theme_selector.label == "Theme"
    assert theme_selector.value == "Forest"
    assert list(theme_selector.options) == ["Light", "Dark", "Forest"]
    # Datasets are chosen from the library dialog; the active choice lives in session state.
    assert any(button.label == "Dataset library" for button in app.sidebar.button)
    raster_label = next(label for label in app.session_state["panda_dataset_labels"] if "TreeMap_2022.tif" in label)
    app.session_state["dataset_selector"] = raster_label
    app = app.run()

    assert not app.exception
    assert any("Raster overview" in heading.value for heading in app.subheader)
    assert any("EPSG:5070" in info.value for info in app.info)
    assert any("TM_ID" in info.value for info in app.info)
    assert not any("does not include a band description" in info.value for info in app.info)
    metric_labels = {metric.label for metric in app.metric}
    assert {"Valid pixels", "Distinct values", "Minimum TM_ID", "Maximum TM_ID"}.issubset(metric_labels)
    expander_labels = {expander.label for expander in app.expander}
    assert {"Mapped forest types", "Raster attribute table", "Raster product documentation"}.issubset(expander_labels)

    with sqlite3.connect("storage/canopy.sqlite") as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        saved_chat_count = connection.execute(
            "SELECT COUNT(*) FROM chat_conversations"
        ).fetchone()[0]

    assert {"chat_conversations", "chat_messages"}.issubset(tables)
    assert saved_chat_count >= 1
