import os
import random
import string
import pytest  # type: ignore
from google.cloud import storage
from google.api_core.exceptions import NotFound

from replicate.exceptions import DoesNotExistError
from replicate.storage.gcs_storage import GCSStorage


# Disable this test with -m "not external"
pytestmark = pytest.mark.external

# We only create one bucket for these tests, because Google Cloud rate limits creating buckets
# https://cloud.google.com/storage/quotas
# This means these tests can't be run in parallel
@pytest.fixture(scope="session")
def temp_bucket_create():
    bucket_name = "replicate-test-" + "".join(
        random.choice(string.ascii_lowercase) for _ in range(20)
    )

    client = storage.Client()
    bucket = client.create_bucket(bucket_name)
    try:
        bucket.reload()
        assert bucket.exists()
        yield bucket
    finally:
        bucket.delete(force=True)


@pytest.fixture(scope="function")
def temp_bucket(temp_bucket_create):
    bucket = temp_bucket_create
    # Clear bucket before each test
    blobs = bucket.list_blobs()
    for blob in blobs:
        blob.delete()
    yield bucket


def test_put_get(temp_bucket):
    storage = GCSStorage(bucket=temp_bucket.name, root="")
    storage.put("foo/bar.txt", "nice")
    assert temp_bucket.blob("foo/bar.txt").download_as_bytes() == b"nice"
    assert storage.get("foo/bar.txt") == b"nice"


def test_put_get_with_root(temp_bucket):
    storage = GCSStorage(bucket=temp_bucket.name, root="someroot")
    storage.put("foo/bar.txt", "nice")
    assert temp_bucket.blob("someroot/foo/bar.txt").download_as_bytes() == b"nice"
    assert storage.get("foo/bar.txt") == b"nice"


def test_get_not_exists(temp_bucket):
    storage = GCSStorage(bucket=temp_bucket.name, root="")
    with pytest.raises(DoesNotExistError):
        assert storage.get("foo/bar.txt")


def test_list(temp_bucket):
    storage = GCSStorage(bucket=temp_bucket.name, root="")
    storage.put("foo", "nice")
    storage.put("some/bar", "nice")
    assert storage.list("") == ["foo"]
    assert storage.list("some") == ["some/bar"]


def test_put_path(temp_bucket, tmpdir):
    storage = GCSStorage(bucket=temp_bucket.name, root="")

    for path in ["foo.txt", "bar/baz.txt", "qux.txt"]:
        abs_path = os.path.join(tmpdir, path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w") as f:
            f.write("hello " + path)

    storage.put_path(tmpdir, "folder")
    assert temp_bucket.blob("folder/foo.txt").download_as_bytes() == b"hello foo.txt"
    assert temp_bucket.blob("folder/qux.txt").download_as_bytes() == b"hello qux.txt"
    assert (
        temp_bucket.blob("folder/bar/baz.txt").download_as_bytes()
        == b"hello bar/baz.txt"
    )

    # single files
    storage.put_path(os.path.join(tmpdir, "foo.txt"), "singlefile/foo.txt")
    assert (
        temp_bucket.blob("singlefile/foo.txt").download_as_bytes() == b"hello foo.txt"
    )


def test_put_path_with_root(temp_bucket, tmpdir):
    storage = GCSStorage(bucket=temp_bucket.name, root="someroot")

    for path in ["foo.txt", "bar/baz.txt", "qux.txt"]:
        abs_path = os.path.join(tmpdir, path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w") as f:
            f.write("hello " + path)

    storage.put_path(tmpdir, "folder")
    assert (
        temp_bucket.blob("someroot/folder/foo.txt").download_as_bytes()
        == b"hello foo.txt"
    )
    assert (
        temp_bucket.blob("someroot/folder/qux.txt").download_as_bytes()
        == b"hello qux.txt"
    )
    assert (
        temp_bucket.blob("someroot/folder/bar/baz.txt").download_as_bytes()
        == b"hello bar/baz.txt"
    )

    # single files
    storage.put_path(os.path.join(tmpdir, "foo.txt"), "singlefile/foo.txt")
    assert (
        temp_bucket.blob("someroot/singlefile/foo.txt").download_as_bytes()
        == b"hello foo.txt"
    )


def test_replicateignore(temp_bucket, tmpdir):
    storage = GCSStorage(bucket=temp_bucket.name, root="")

    for path in [
        "foo.txt",
        "bar/baz.txt",
        "bar/quux.xyz",
        "bar/new-qux.txt",
        "qux.xyz",
    ]:
        abs_path = os.path.join(tmpdir, path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w") as f:
            f.write("hello " + path)

    with open(os.path.join(tmpdir, ".replicateignore"), "w") as f:
        f.write(
            """
# this is a comment
baz.txt
*.xyz
"""
        )

    storage.put_path(tmpdir, "folder")
    assert temp_bucket.blob("folder/foo.txt").download_as_bytes() == b"hello foo.txt"
    assert (
        temp_bucket.blob("folder/bar/new-qux.txt").download_as_bytes()
        == b"hello bar/new-qux.txt"
    )
    with pytest.raises(NotFound):
        temp_bucket.blob("folder/bar/baz.txt").download_as_bytes()
    with pytest.raises(NotFound):
        temp_bucket.blob("folder/qux.xyz").download_as_bytes()
    with pytest.raises(NotFound):
        temp_bucket.blob("folder/bar/quux.xyz").download_as_bytes()


def test_delete(temp_bucket, tmpdir):
    storage = GCSStorage(bucket=temp_bucket.name, root="")

    storage.put("some/file", "nice")
    assert storage.get("some/file") == b"nice"

    storage.delete("some/file")
    with pytest.raises(DoesNotExistError):
        storage.get("some/file")


def test_delete_with_root(temp_bucket, tmpdir):
    storage = GCSStorage(bucket=temp_bucket.name, root="my-root")

    storage.put("some/file", "nice")
    assert storage.get("some/file") == b"nice"

    storage.delete("some/file")
    with pytest.raises(DoesNotExistError):
        storage.get("some/file")