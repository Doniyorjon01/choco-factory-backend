"""
Xato va xabar matnlari (oʻzbek va rus tillarida).

`Msg` qiymati API javobidagi `code` maydoni bo'ladi. Frontend mantiqni
shu kodga qarab quradi, matnni esa faqat foydalanuvchiga ko'rsatadi.
Shuning uchun kodlarni o'zgartirmang, faqat yangisini qo'shing.

Matnlarda {nom} ko'rinishidagi parametrlar bo'lishi mumkin.
Oʻzbek imlosida oʻ/gʻ faqat ʻ (U+02BB) bilan yoziladi.
"""

from enum import Enum

from utils.i18n import DEFAULT_LANG, Lang


class Msg(str, Enum):
    # --- umumiy ---
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    FORBIDDEN = "FORBIDDEN"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

    # --- auth ---
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    USER_INACTIVE = "USER_INACTIVE"
    PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"
    WRONG_CURRENT_PASSWORD = "WRONG_CURRENT_PASSWORD"
    PASSWORD_SAME_AS_OLD = "PASSWORD_SAME_AS_OLD"

    # --- foydalanuvchilar ---
    USER_NOT_FOUND = "USER_NOT_FOUND"
    LOGIN_TAKEN = "LOGIN_TAKEN"
    CANNOT_MODIFY_SELF = "CANNOT_MODIFY_SELF"
    LAST_ADMIN = "LAST_ADMIN"

    # --- mahsulotlar ---
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    PRODUCT_CODE_TAKEN = "PRODUCT_CODE_TAKEN"
    PRODUCT_CODE_PREFIX = "PRODUCT_CODE_PREFIX"
    PRODUCT_NAME_TAKEN = "PRODUCT_NAME_TAKEN"
    PRODUCT_ARCHIVED = "PRODUCT_ARCHIVED"
    PRODUCT_HAS_STOCK = "PRODUCT_HAS_STOCK"
    PRODUCT_USED_IN_ACTIVE_RECIPE = "PRODUCT_USED_IN_ACTIVE_RECIPE"
    PRODUCT_NOT_FINISHED = "PRODUCT_NOT_FINISHED"
    PRODUCT_NOT_RAW = "PRODUCT_NOT_RAW"
    TARGET_BELOW_MIN = "TARGET_BELOW_MIN"

    # --- retseptlar ---
    RECIPE_VERSION_NOT_FOUND = "RECIPE_VERSION_NOT_FOUND"
    RECIPE_DRAFT_EXISTS = "RECIPE_DRAFT_EXISTS"
    RECIPE_NOT_DRAFT = "RECIPE_NOT_DRAFT"
    RECIPE_EMPTY = "RECIPE_EMPTY"
    RECIPE_DUPLICATE_LINE = "RECIPE_DUPLICATE_LINE"
    NO_ACTIVE_RECIPE = "NO_ACTIVE_RECIPE"

    # --- documents ---
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    RECIPE_VERSION_CHANGED = "RECIPE_VERSION_CHANGED"
    STOCK_CHANGED = "STOCK_CHANGED"
    NEGATIVE_BALANCE = "NEGATIVE_BALANCE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    ALREADY_REVERSED = "ALREADY_REVERSED"
    CANNOT_REVERSE_REVERSAL = "CANNOT_REVERSE_REVERSAL"
    SUPPLIER_DATE_IN_FUTURE = "SUPPLIER_DATE_IN_FUTURE"
    NOTE_REQUIRED = "NOTE_REQUIRED"
    ADJUSTMENT_NO_DIFF = "ADJUSTMENT_NO_DIFF"
    SCRAP_KIND_FORBIDDEN = "SCRAP_KIND_FORBIDDEN"
    DUPLICATE_LINE = "DUPLICATE_LINE"
    LOCK_TIMEOUT = "LOCK_TIMEOUT"
    RECEIPT_RAW_ONLY = "RECEIPT_RAW_ONLY"
    INVALID_REASON = "INVALID_REASON"


_TEXTS: dict[Msg, dict[Lang, str]] = {
    Msg.UNKNOWN_ERROR: {
        Lang.uz: "Kutilmagan xato. Hech narsa oʻzgarmadi — qayta urinib koʻring.",
        Lang.ru: "Непредвиденная ошибка. Ничего не изменилось — попробуйте ещё раз.",
    },
    Msg.VALIDATION_ERROR: {
        Lang.uz: "Maʼlumotlar notoʻgʻri toʻldirilgan.",
        Lang.ru: "Данные заполнены неверно.",
    },
    Msg.NOT_FOUND: {Lang.uz: "Topilmadi.", Lang.ru: "Не найдено."},
    Msg.METHOD_NOT_ALLOWED: {Lang.uz: "Bu amal ruxsat etilmagan.", Lang.ru: "Метод не разрешён."},
    Msg.CONFLICT: {
        Lang.uz: "Maʼlumotlar boshqa amal bilan toʻqnashdi. Sahifani yangilab, qayta urinib koʻring.",
        Lang.ru: "Конфликт с другой операцией. Обновите страницу и попробуйте снова.",
    },
    Msg.FORBIDDEN: {Lang.uz: "Bu boʻlimga ruxsat yoʻq.", Lang.ru: "Нет доступа к этому разделу."},
    Msg.SERVICE_UNAVAILABLE: {
        Lang.uz: "Xizmat vaqtincha ishlamayapti.",
        Lang.ru: "Сервис временно недоступен.",
    },
    Msg.NOT_AUTHENTICATED: {Lang.uz: "Tizimga kiring.", Lang.ru: "Войдите в систему."},
    Msg.INVALID_CREDENTIALS: {
        Lang.uz: "Login yoki parol notoʻgʻri.",
        Lang.ru: "Неверный логин или пароль.",
    },
    Msg.TOKEN_INVALID: {
        Lang.uz: "Sessiya yaroqsiz. Qayta kiring.",
        Lang.ru: "Сессия недействительна. Войдите снова.",
    },
    Msg.TOKEN_EXPIRED: {
        Lang.uz: "Sessiya muddati tugadi. Qayta kiring.",
        Lang.ru: "Сессия истекла. Войдите снова.",
    },
    Msg.ACCOUNT_LOCKED: {
        Lang.uz: "Juda koʻp notoʻgʻri urinish. {minutes} daqiqadan keyin qayta urinib koʻring.",
        Lang.ru: "Слишком много неудачных попыток. Повторите через {minutes} мин.",
    },
    Msg.USER_INACTIVE: {
        Lang.uz: "Hisobingiz bloklangan. Administratorga murojaat qiling.",
        Lang.ru: "Ваша учётная запись заблокирована. Обратитесь к администратору.",
    },
    Msg.PASSWORD_CHANGE_REQUIRED: {
        Lang.uz: "Davom etish uchun parolni almashtiring.",
        Lang.ru: "Чтобы продолжить, смените пароль.",
    },
    Msg.WRONG_CURRENT_PASSWORD: {
        Lang.uz: "Joriy parol notoʻgʻri.",
        Lang.ru: "Текущий пароль неверен.",
    },
    Msg.PASSWORD_SAME_AS_OLD: {
        Lang.uz: "Yangi parol eskisidan farq qilishi kerak.",
        Lang.ru: "Новый пароль должен отличаться от старого.",
    },
    Msg.USER_NOT_FOUND: {Lang.uz: "Foydalanuvchi topilmadi.", Lang.ru: "Пользователь не найден."},
    Msg.LOGIN_TAKEN: {Lang.uz: "Bu login band.", Lang.ru: "Этот логин уже занят."},
    Msg.CANNOT_MODIFY_SELF: {
        Lang.uz: "Oʻzingizning rolingizni oʻzgartirib yoki oʻzingizni bloklab boʻlmaydi.",
        Lang.ru: "Нельзя менять свою роль или блокировать себя.",
    },
    Msg.LAST_ADMIN: {
        Lang.uz: "Tizimda kamida bitta faol administrator qolishi kerak.",
        Lang.ru: "В системе должен остаться хотя бы один активный администратор.",
    },
    Msg.PRODUCT_NOT_FOUND: {Lang.uz: "Mahsulot topilmadi.", Lang.ru: "Продукт не найден."},
    Msg.PRODUCT_CODE_TAKEN: {Lang.uz: "Bu kod band: {code}.", Lang.ru: "Этот код уже занят: {code}."},
    Msg.PRODUCT_CODE_PREFIX: {
        Lang.uz: "Kod {prefix}- bilan boshlanishi kerak (masalan, {prefix}-006).",
        Lang.ru: "Код должен начинаться с {prefix}- (например, {prefix}-006).",
    },
    Msg.PRODUCT_NAME_TAKEN: {
        Lang.uz: "Shu nomli mahsulot allaqachon bor.",
        Lang.ru: "Продукт с таким названием уже существует.",
    },
    Msg.PRODUCT_ARCHIVED: {
        Lang.uz: "Mahsulot arxivda: {name}.",
        Lang.ru: "Продукт в архиве: {name}.",
    },
    Msg.PRODUCT_HAS_STOCK: {
        Lang.uz: "Omborda qoldiq bor ({qty}). Avval tuzatish yoki brak bilan nolga tushiring.",
        Lang.ru: "На складе есть остаток ({qty}). Сначала обнулите его корректировкой или списанием.",
    },
    Msg.PRODUCT_USED_IN_ACTIVE_RECIPE: {
        Lang.uz: "Bu xomashyo faol retseptlarda ishlatiladi: {products}.",
        Lang.ru: "Это сырьё используется в активных рецептах: {products}.",
    },
    Msg.PRODUCT_NOT_FINISHED: {
        Lang.uz: "Retsept faqat tayyor mahsulot uchun tuziladi.",
        Lang.ru: "Рецепт составляется только для готовой продукции.",
    },
    Msg.PRODUCT_NOT_RAW: {
        Lang.uz: "Retsept tarkibida faqat xomashyo boʻlishi mumkin.",
        Lang.ru: "В составе рецепта может быть только сырьё.",
    },
    Msg.TARGET_BELOW_MIN: {
        Lang.uz: "Maqsadli zaxira minimal qoldiqdan kam boʻlmasligi kerak.",
        Lang.ru: "Целевой запас не может быть меньше минимального остатка.",
    },
    Msg.RECIPE_VERSION_NOT_FOUND: {
        Lang.uz: "Retsept versiyasi topilmadi.",
        Lang.ru: "Версия рецепта не найдена.",
    },
    Msg.RECIPE_DRAFT_EXISTS: {
        Lang.uz: "Bu mahsulotda qoralama allaqachon bor (v{version}).",
        Lang.ru: "У этого продукта уже есть черновик (v{version}).",
    },
    Msg.RECIPE_NOT_DRAFT: {
        Lang.uz: "Faqat qoralamani oʻzgartirish mumkin. Faol versiya tahrirlanmaydi.",
        Lang.ru: "Изменять можно только черновик. Активная версия не редактируется.",
    },
    Msg.RECIPE_EMPTY: {
        Lang.uz: "Retseptda kamida bitta xomashyo boʻlishi kerak.",
        Lang.ru: "В рецепте должно быть хотя бы одно сырьё.",
    },
    Msg.RECIPE_DUPLICATE_LINE: {
        Lang.uz: "Bitta xomashyo retseptda ikki marta kelgan.",
        Lang.ru: "Одно и то же сырьё указано в рецепте дважды.",
    },
    Msg.NO_ACTIVE_RECIPE: {
        Lang.uz: "Bu mahsulotning faol retsepti yoʻq.",
        Lang.ru: "У этого продукта нет активного рецепта.",
    },
    Msg.DOCUMENT_NOT_FOUND: {Lang.uz: "Hujjat topilmadi.", Lang.ru: "Документ не найден."},
    Msg.INSUFFICIENT_STOCK: {
        Lang.uz: "Omborda yetarli qoldiq yoʻq. Hech narsa yozilmadi.",
        Lang.ru: "Недостаточно остатка на складе. Ничего не записано.",
    },
    Msg.RECIPE_VERSION_CHANGED: {
        Lang.uz: "Retsept yangilandi: v{old} → v{new}. Hech narsa yozilmadi.",
        Lang.ru: "Рецепт обновлён: v{old} → v{new}. Ничего не записано.",
    },
    Msg.STOCK_CHANGED: {
        Lang.uz: "Qoldiq oʻzgardi, qayta sanang yoki tasdiqlang. Hech narsa saqlanmadi.",
        Lang.ru: "Остаток изменился — пересчитайте или подтвердите. Ничего не сохранено.",
    },
    Msg.NEGATIVE_BALANCE: {
        Lang.uz: "Storno qoldiqni manfiy qiladi. Rad etildi.",
        Lang.ru: "Сторно сделает остаток отрицательным. Отклонено.",
    },
    Msg.IDEMPOTENCY_CONFLICT: {
        Lang.uz: "Bu soʻrov ID boshqa maʼlumot bilan allaqachon ishlatilgan.",
        Lang.ru: "Этот ID запроса уже использован с другими данными.",
    },
    Msg.ALREADY_REVERSED: {
        Lang.uz: "Hujjat allaqachon storno qilingan: {number}.",
        Lang.ru: "Документ уже сторнирован: {number}.",
    },
    Msg.CANNOT_REVERSE_REVERSAL: {
        Lang.uz: "Storno hujjatini storno qilib boʻlmaydi.",
        Lang.ru: "Документ сторно нельзя сторнировать.",
    },
    Msg.SUPPLIER_DATE_IN_FUTURE: {
        Lang.uz: "Yetkazib beruvchi hujjati sanasi kelajakda boʻlmasligi kerak.",
        Lang.ru: "Дата документа поставщика не может быть в будущем.",
    },
    Msg.NOTE_REQUIRED: {
        Lang.uz: "«Boshqa» tanlansa, izoh majburiy.",
        Lang.ru: "При выборе «Другое» комментарий обязателен.",
    },
    Msg.ADJUSTMENT_NO_DIFF: {
        Lang.uz: "Farq yoʻq — tuzatish kerak emas.",
        Lang.ru: "Расхождения нет — корректировка не нужна.",
    },
    Msg.SCRAP_KIND_FORBIDDEN: {
        Lang.uz: "Operator faqat tayyor mahsulotni brak qila oladi.",
        Lang.ru: "Оператор может списывать только готовую продукцию.",
    },
    Msg.DUPLICATE_LINE: {
        Lang.uz: "Bitta mahsulot hujjatda ikki marta kelgan.",
        Lang.ru: "Один и тот же продукт указан в документе дважды.",
    },
    Msg.RECEIPT_RAW_ONLY: {
        Lang.uz: "Kirim faqat xomashyo uchun. Tayyor mahsulot ishlab chiqarish orqali keladi.",
        Lang.ru: "Приход только для сырья. Готовая продукция поступает через производство.",
    },
    Msg.INVALID_REASON: {
        Lang.uz: "Bu sabab ushbu amal uchun mos emas.",
        Lang.ru: "Эта причина не подходит для данной операции.",
    },
    Msg.LOCK_TIMEOUT: {
        Lang.uz: "Ombor band — boshqa amal tugashini kutib boʻlmadi. Qayta urinib koʻring.",
        Lang.ru: "Склад занят другой операцией. Попробуйте ещё раз.",
    },
}


def translate(msg: Msg, lang: Lang = DEFAULT_LANG, params: dict | None = None) -> str:
    texts = _TEXTS.get(msg)
    if texts is None:
        return msg.value
    text = texts.get(lang) or texts[DEFAULT_LANG]
    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            # Parametr yetishmasa ham xabar yo'qolmasin
            return text
    return text