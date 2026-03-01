from sel_bot.media_utils import (
    looks_like_gif_url,
    looks_like_image_filename,
    looks_like_image_url,
    normalize_content_type,
    url_extension,
)


def test_normalize_content_type() -> None:
    assert normalize_content_type("image/gif; charset=utf-8") == "image/gif"
    assert normalize_content_type("IMAGE/PNG") == "image/png"
    assert normalize_content_type(None) is None


def test_url_extension_prefers_path_suffix() -> None:
    assert url_extension("https://example.com/image.png?format=gif") == ".png"
    assert url_extension("https://example.com/assets/photo.jpeg") == ".jpeg"


def test_url_extension_uses_query_fallback() -> None:
    assert url_extension("https://example.com/image?format=gif") == ".gif"
    assert url_extension("https://example.com/photo?ext=webp") == ".webp"


def test_looks_like_image_url() -> None:
    assert looks_like_image_url("https://example.com/photo.jpg")
    assert looks_like_image_url("https://example.com/photo?format=png")
    assert not looks_like_image_url("https://example.com/readme.txt")


def test_looks_like_gif_url() -> None:
    assert looks_like_gif_url("https://example.com/anim.gif")
    assert looks_like_gif_url("https://example.com/anim?format=gif")
    assert looks_like_gif_url("https://example.com/anim.png", "image/gif")
    assert not looks_like_gif_url("https://example.com/anim.png")


def test_looks_like_image_filename() -> None:
    assert looks_like_image_filename("PHOTO.JPEG")
    assert not looks_like_image_filename("notes.txt")
