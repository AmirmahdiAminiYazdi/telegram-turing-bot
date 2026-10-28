from bot.services import cards


def P(**kw):
    base = dict(id=1, title="دوره <پایتون>", description="توضیح کوتاه", price=900_000,
                list_price=900_000, on_sale=0, sale_left=0, sold=0, rating=None,
                rating_count=0, seats=None, seats_left=None, features=None,
                guarantee=None, preview_url=None, cover_file_id=None)
    base.update(kw)
    return base


def test_no_fake_social_proof_below_thresholds():
    text = cards.product_card(P(sold=4, rating=5.0, rating_count=2))
    assert "نفر" not in text and "⭐" not in text


def test_social_proof_shown_when_real_enough():
    text = cards.product_card(P(sold=124, rating=4.8, rating_count=23))
    assert "⭐ 4.8 (23 نظر)" in text and "124 نفر" in text


def test_sale_shows_strikethrough_and_countdown():
    text = cards.product_card(P(price=600_000, list_price=900_000, on_sale=1, sale_left=2 * 86400 + 3 * 3600))
    assert "<s>900,000</s>" in text and "600,000" in text and "2 روز و 3 ساعت" in text


def test_seats_and_sold_out():
    assert "3 جای خالی از 20" in cards.product_card(P(seats=20, seats_left=3))
    assert cards.sold_out(P(seats=20, seats_left=0)) and not cards.sold_out(P())
    assert "تکمیل" in cards.product_card(P(seats=20, seats_left=0))


def test_html_is_escaped_and_features_listed():
    text = cards.product_card(P(features="الف\nب <b>\n\n"))
    assert "&lt;پایتون&gt;" in text and "✅ الف" in text and "&lt;b&gt;" in text


def test_caption_limit_truncates_description_only():
    text = cards.product_card(P(description="الف" * 3000, guarantee="ضمانت ۷ روزه"), limit=1000)
    assert len(text) <= 1000 and "ضمانت ۷ روزه" in text and text.count("…") == 1


def test_time_left_formats():
    assert cards.time_left(30) == "1 دقیقه"
    assert cards.time_left(3 * 3600 + 120) == "3 ساعت و 2 دقیقه"


def test_catalog_label_badges():
    assert cards.catalog_label(P(id=2), 2).startswith("🔥")
    assert cards.catalog_label(P(on_sale=1), None).startswith("🏷")
    assert cards.catalog_label(P(seats=1, seats_left=0), None).endswith("⛔")
