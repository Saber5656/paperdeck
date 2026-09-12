from paperdeck.engines.latex.graphics import jpeg_dimensions, png_dimensions


def test_image_dimension_header_parsers() -> None:
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + (800).to_bytes(4, "big")
        + (600).to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    assert png_dimensions(png) == (800, 600)
    jpeg = (
        b"\xff\xd8\xff\xc0\x00\x11\x08"
        + (600).to_bytes(2, "big")
        + (800).to_bytes(2, "big")
        + b"\x03"
        + b"\x01\x11\x00" * 3
    )
    assert jpeg_dimensions(jpeg) == (800, 600)
