from ebay_mcp_server.title_validation import validate_titles


def valid_titles(count=30):
    return [
        f"Wireless Earbuds Bluetooth Charging Case Touch Control Series {index}"
        for index in range(1, count + 1)
    ]


def test_thirty_mechanically_valid_titles_pass():
    result = validate_titles(valid_titles())
    assert result["received_count"] == 30
    assert result["valid_count"] == 30
    assert result["valid_for_delivery"] is True


def test_count_is_a_hard_delivery_requirement():
    result = validate_titles(valid_titles(29))
    assert result["valid_for_delivery"] is False
    assert result["global_issues"][0]["code"] == "TITLE_COUNT_MISMATCH"


def test_length_punctuation_repeated_word_and_duplicate_are_reported():
    titles = valid_titles()
    titles[0] = "Earbuds Earbuds Wireless"
    titles[1] = "Wireless Earbuds, Bluetooth"
    titles[2] = "X" * 81
    titles[3] = titles[4]
    result = validate_titles(titles)
    codes = {
        issue["code"]
        for row in result["titles"]
        for issue in row["issues"]
    }
    assert {
        "REPEATED_WORD",
        "UNSUPPORTED_PUNCTUATION",
        "TITLE_TOO_LONG",
        "DUPLICATE_TITLE",
    } <= codes
    assert result["valid_for_delivery"] is False


def test_forbidden_terms_are_caller_supplied_and_boundary_aware():
    titles = valid_titles()
    titles[0] = "Sony Wireless Earbuds Bluetooth Charging Case Series 1"
    titles[1] = "PRO4 Wireless Earbuds Bluetooth Charging Case Series 2"
    result = validate_titles(titles, forbidden_terms=["Sony", "PRO4"])
    assert result["titles"][0]["issues"][0]["code"] == "FORBIDDEN_TERM"
    assert result["titles"][1]["issues"][0]["code"] == "FORBIDDEN_TERM"


def test_short_title_is_warning_not_mechanical_failure():
    titles = valid_titles()
    titles[0] = "Wireless Earbuds"
    result = validate_titles(titles)
    assert result["titles"][0]["valid"] is True
    assert result["titles"][0]["warnings"][0]["code"] == "SHORT_TITLE"

