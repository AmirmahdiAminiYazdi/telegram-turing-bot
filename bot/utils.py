_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_SEPARATORS = str.maketrans("", "", ",،٬ ‌‏‎")


def parse_int(raw: str) -> int | None:
    """عدد با ارقام فارسی/عربی و جداکننده‌های هزارگان (، , ٬) -> int؛ نامعتبر -> None."""
    s = raw.translate(_DIGITS).translate(_SEPARATORS)
    return int(s) if s.isdigit() else None
