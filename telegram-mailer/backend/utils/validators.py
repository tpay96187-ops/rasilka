import re

def validate_phone(phone: str) -> bool:
    """
    Проверяет, является ли строка корректным номером телефона в международном формате.
    Например: +79123456789, 79123456789 (без +) или с пробелами/дефисами.
    """
    # Удаляем все нецифровые символы, кроме ведущего '+'
    cleaned = re.sub(r'[^\d+]', '', phone)
    # Проверяем: начинается с '+' или с цифры, длина 10-15 цифр
    if cleaned.startswith('+'):
        digits = cleaned[1:]
        if digits.isdigit() and 10 <= len(digits) <= 14:
            return True
    else:
        if cleaned.isdigit() and 10 <= len(cleaned) <= 15:
            return True
    return False
