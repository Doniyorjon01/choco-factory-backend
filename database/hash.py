import bcrypt

# bcrypt faqat birinchi 72 baytni hisobga oladi. Sxemada parol uzunligi
# 72 baytdan oshmasligi tekshiriladi, bu yerda esa oxirgi himoya.
_MAX_BYTES = 72

# Mavjud bo'lmagan login uchun ham verify bajariladi — javob vaqti bo'yicha
# "bunday foydalanuvchi bormi" degan savolga javob chiqib qolmasin.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(rounds=12))


class Hash:
    @staticmethod
    def bcrypt(password: str) -> str:
        raw = password.encode("utf-8")[:_MAX_BYTES]
        return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")

    @staticmethod
    def verify(hashed_password: str, plain_password: str) -> bool:
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8")[:_MAX_BYTES], hashed_password.encode("ascii"))
        except ValueError:
            return False

    @staticmethod
    def dummy_verify(plain_password: str) -> None:
        bcrypt.checkpw(plain_password.encode("utf-8")[:_MAX_BYTES], _DUMMY_HASH)
