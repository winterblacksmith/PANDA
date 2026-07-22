import sqlite3

from streamlit.testing.v1 import AppTest


def test_geotiff_is_available_and_opens_from_dataset_selector():
    app = AppTest.from_file("app.py", default_timeout=30).run()

    assert not app.exception
    assert not any(expander.label == "Raster layers" for expander in app.expander)
    assert any(expander.label == "SQLite database preview" for expander in app.expander)
    dataset_selector = app.sidebar.selectbox[0]
    assert any("TreeMap_2022.tif" in str(option) for option in dataset_selector.options)

    raster_index = next(
        index for index, option in enumerate(dataset_selector.options)
        if "TreeMap_2022.tif" in str(option)
    )
    app = dataset_selector.select_index(raster_index).run()

    assert not app.exception
    assert any("Raster overview" in heading.value for heading in app.subheader)
    assert any("EPSG:5070" in info.value for info in app.info)
    metric_labels = {metric.label for metric in app.metric}
    assert {"Valid pixels", "Distinct values", "Minimum", "Maximum"}.issubset(metric_labels)

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
