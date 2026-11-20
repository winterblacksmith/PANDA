from pathlib import Path

import pytest

import dataset_library as lib


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PANDA_STORAGE_DIR", str(tmp_path / "storage"))
    for name in ("RAILWAY_VOLUME_MOUNT_PATH", "RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_csv_upload_goes_to_persistent_library_and_is_listed(storage):
    saved, errors = lib.save_uploads([("trees.csv", b"Species,DBH\nOak,10\n")], [])
    assert not errors and saved == [lib.library_dir() / "csv" / "trees.csv"]
    items = lib.list_items(storage / "nodata", storage / "norasters", [])
    assert [(i.name, i.kind, i.source) for i in items] == [("trees.csv", "csv", "Uploaded")]


def test_csv_with_shapefile_becomes_fvs_dataset(storage):
    files = [("stands.csv", b"MU_ID,Age\n1,30\n"), ("stands.shp", b"x"), ("stands.shx", b"x"),
             ("stands.dbf", b"x"), ("stands.prj", b"x"), ("other.shx", b"x")]
    saved, errors = lib.save_uploads(files, [])
    assert saved == [lib.library_dir() / "fvs" / "stands.csv"]
    assert any("other.shx" in e for e in errors)  # companion without its main file
    items = lib.list_items(storage / "nodata", storage / "norasters", [])
    assert items[0].kind == "fvs" and items[0].kind_label == "FVS stands + polygons"


def test_duplicate_and_bad_csv_rejected(storage):
    _, errors = lib.save_uploads([("trees.csv", b"a,b\n1,2\n")], ["Trees.csv"])
    assert "already in the library" in errors[0]
    _, errors = lib.save_uploads([("empty.csv", b"")], [])
    assert "empty" in errors[0]


def test_raster_upload_keeps_companions_and_delete_removes_them(storage):
    saved, errors = lib.save_uploads([("map.tif", b"II*\x00"), ("map.tfw", b"1"), ("map.tif.aux.xml", b"<x/>")], [])
    assert not errors
    raster_dir = lib.library_raster_dir()
    assert sorted(p.name for p in raster_dir.iterdir()) == ["map.tfw", "map.tif", "map.tif.aux.xml"]
    item = lib.list_items(storage / "nodata", storage / "norasters", [raster_dir / "map.tif"])[0]
    assert item.source == "Uploaded"
    lib.delete_item(item)
    assert list(raster_dir.iterdir()) == []


def test_builtin_datasets_cannot_be_deleted(storage):
    data = storage / "data"
    data.mkdir()
    (data / "built.csv").write_text("a\n1\n")
    item = lib.list_items(data, storage / "norasters", [])[0]
    assert item.source == "Built-in"
    with pytest.raises(PermissionError):
        lib.delete_item(item)
    assert (data / "built.csv").exists()


def test_storage_status_detects_railway_volume(monkeypatch, storage):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    assert lib.storage_status()["persistent"] is False
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(storage / "storage"))
    assert lib.storage_status()["persistent"] is True
