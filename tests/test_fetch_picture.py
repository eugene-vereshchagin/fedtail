"""A picture into the shared disk cache (common/images.fetch_picture, the web page's
/pic): by its bytes, not by the type the server names — custom emoji kept on S3 come as
application/octet-stream and stood as :code: on the page (29.10)."""

import contextlib
import io
import tempfile
import unittest

from fedtail.frontends.common import images


def png():
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(out, "PNG")
    return out.getvalue()


class Answer:
    def __init__(self, data, kind):
        self.data, self.headers = data, {"Content-Type": kind,
                                         "Content-Length": str(len(data))}

    def raise_for_status(self):
        pass

    def iter_content(self, _n):
        yield self.data


def opener(data, kind):
    return lambda _url, timeout: contextlib.nullcontext(Answer(data, kind))


class FetchPictureTest(unittest.TestCase):
    def test_by_the_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            got = images.fetch_picture(d, "https://s3.example/e.png",
                                       opener(png(), "application/octet-stream"))
            self.assertIsNotNone(got)  # a picture whatever it was called
            self.assertIsNone(images.fetch_picture(
                d, "https://x.example/page", opener(b"<html>no</html>", "text/html")))
            self.assertIsNone(images.fetch_picture(  # not a picture: never kept
                d, "https://x.example/blob", opener(b"\0" * 64, "application/octet-stream")))


if __name__ == "__main__":
    unittest.main()
