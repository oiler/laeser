from naming import slugify, date_prefix, entry_base


def test_slugify_basic():
    assert slugify("Hello World!") == "hello-world"


def test_slugify_punctuation_and_parens():
    assert slugify("The XZ Backdoor (2024)") == "the-xz-backdoor-2024"


def test_slugify_truncates_to_80_chars():
    long = "A" * 100
    assert len(slugify(long)) == 80


def test_slugify_collapses_whitespace_and_underscores():
    assert slugify("foo___bar   baz") == "foo-bar-baz"


def test_slugify_strips_unicode_punctuation():
    assert slugify("Café — bonjour") == "café-bonjour"


def test_slugify_empty_string():
    assert slugify("") == ""


def test_date_prefix_uses_pub_date_prefix():
    assert date_prefix("2024-04-02T10:00:00Z") == "2024-04-02"


def test_date_prefix_empty_falls_back_to_today():
    out = date_prefix("")
    assert len(out) == 10
    assert out[4] == "-" and out[7] == "-"


def test_date_prefix_none_falls_back_to_today():
    out = date_prefix(None)
    assert len(out) == 10


def test_entry_base_combines_date_and_slug():
    assert entry_base("Hello World!", "2024-04-02") == "2024-04-02-hello-world"


def test_entry_base_with_missing_date_uses_today():
    out = entry_base("Hello World!", None)
    assert out.endswith("-hello-world")
    assert len(out) == len("YYYY-MM-DD-hello-world")
