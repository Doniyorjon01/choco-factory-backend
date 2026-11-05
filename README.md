# Chocolate Factory — Mini-MRP backend

Kichik shokolad ishlab chiqaruvchisi uchun ombor va ishlab chiqarish hisobi.
Stek: FastAPI · SQLAlchemy 2 (sync) · PostgreSQL 16 · Alembic · Docker.

> **Holat: 1-qism (poydevor).** Tayyor: auth va rollar, foydalanuvchilar, mahsulotlar,
> retsept versiyalari, qoldiqlar va ishlab chiqarish imkoniyati, butun baza sxemasi.
> **2-qism:** hujjatlar (kirim, ishlab chiqarish, tuzatish, brak, storno), jurnal,
> dashboard, tarixli seed.

---

## Tez ishga tushirish (Docker)

```bash
cp .env.example .env
# .env ichida POSTGRES_PASSWORD va SECRET_KEY ni to'ldiring:
python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up -d --build          # db → migrate (bir marta) → api
docker compose run --rm api python -m scripts.seed          # demo ma'lumotlar (dev)
# yoki haqiqiy birinchi admin:
docker compose run --rm api python -m scripts.create_admin --login admin --full-name "Ali Valiyev"
```

- API: http://localhost:8000, Swagger: http://localhost:8000/docs (faqat `APP_ENV=dev`)
- Demo loginlar (seed): `admin`, `omborchi`, `operator`, parol — `Kakao2026`

## Lokal ishlab chiqish (Docker'siz, PyCharm)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # DATABASE_URL ni lokal Postgres'ga qarating
alembic upgrade head
python -m scripts.seed
uvicorn main:app --reload
```

Faqat bazani Docker'da ko'tarish mumkin: `docker compose up -d db`.

Lint: `ruff check . && ruff format --check .`

---

## Tuzilma

```
alembic/            migratsiyalar (0001 — butun sxema, cheklovlar, triggerlar)
auth/
  authentication.py /auth/login, /auth/me, /auth/change-password
  oauth2.py         JWT, get_current_user, require_roles(...)
database/
  config.py         engine, SessionLocal, get_pg_db
  hash.py           bcrypt
  db_users.py       foydalanuvchilar bilan ishlash
  db_products.py    mahsulotlar
  db_recipes.py     retsept versiyalari
models/             SQLAlchemy modellari
routers/            users, products, recipes, stock
schemas/            Pydantic v2 sxemalari (kiruvchilarda extra="forbid")
services/stock.py   qoldiqlar va ishlab chiqarish imkoniyati
scripts/            seed, create_admin, check_ledger
utils/              i18n, pagination, logger, timeutils
config.py           sozlamalar (.env)
errors.py           yagona xato formati va global handlerlar
middleware.py       request_id va access log
translations.py     xato kodlari va uz/ru matnlari
```

---

## API (1-qism)

| Metod va yoʻl | Vazifa | Rol |
|---|---|---|
| `POST /auth/login` | Kirish (form: username, password) | hamma |
| `GET/PATCH /auth/me` | Joriy foydalanuvchi; tilni oʻzgartirish | hamma |
| `POST /auth/change-password` | Parol almashtirish → yangi token | hamma |
| `GET/POST /users` | Roʻyxat (q, role, is_active) / yaratish | admin |
| `GET/PATCH /users/{id}` | Koʻrish / ism, rol, til, bloklash | admin |
| `POST /users/{id}/reset-password` | Vaqtinchalik parol, qulfni ochish | admin |
| `GET /products` | Roʻyxat (kind, state, q) + qoldiq | admin, omborchi |
| `POST /products`, `PATCH /products/{id}` | Yaratish / tahrirlash | admin |
| `POST /products/{id}/archive`, `/unarchive` | Arxiv (oʻchirish yoʻq) | admin |
| `GET /recipes` | Tayyor mahsulotlar: faol versiya + qoralama | admin |
| `GET/POST /recipes/products/{id}/versions` | Versiyalar / yangi qoralama | admin |
| `GET/PATCH/DELETE /recipes/versions/{id}` | Koʻrish / qoralamani tahrirlash, oʻchirish | admin |
| `POST /recipes/versions/{id}/activate` | Qoralamani faollashtirish | admin |
| `GET /stock` | Qoldiqlar: daraja, 7 kunlik sarf, necha kunga yetadi | hamma |
| `GET /stock/capacity` | Har bir mahsulotdan maksimal nechta chiqadi | hamma |
| `GET /health`, `/health/ready` | Liveness / readiness (baza + migratsiya) | — |

Roʻyxatlar sahifalanadi: `?page=1&size=20` (koʻpi bilan 100).
Til: `Accept-Language: uz` yoki `ru` (sukut — uz).

### Xato formati

```json
{"detail": {"code": "RECIPE_DRAFT_EXISTS", "message": "Bu mahsulotda qoralama allaqachon bor (v4).", "data": {"draft_id": 4}}}
```

Frontend mantiqni `code` ga qarab quradi, `message` ni koʻrsatadi. Barcha kodlar — `translations.py`.
422 da `data.fields` — maydonlar boʻyicha xatolar.

### Kirish oqimi

1. `POST /auth/login` → `access_token` (12 soat) va `user.must_change_password`.
2. `must_change_password = true` boʻlsa, boshqa endpointlar `403 PASSWORD_CHANGE_REQUIRED`
   qaytaradi — klient faqat parol almashtirish ekranini ochadi.
3. Parol almashtirish, bloklash, rol oʻzgarishi yoki parol tiklashda `token_version`
   oshadi — foydalanuvchining eski tokenlari darhol yaroqsiz boʻladi.
4. 5 ta notoʻgʻri urinish → hisob 5 daqiqaga qulflanadi (`429 ACCOUNT_LOCKED`).

---

## Muhim qarorlar

**Invariantlar bazada, faqat kodda emas.** Kodda xato boʻlsa ham bazaning oʻzi rad etadi:
- `stock_balance.qty >= 0` va jurnalda `qty_after >= 0`;
- `documents`, `ledger_entries`, `production_recipe_snapshot` — faqat INSERT
  (UPDATE, DELETE, TRUNCATE trigger bilan taqiqlangan; tuzatish — faqat storno);
- faol/arxiv retsept tarkibi oʻzgarmaydi, versiya oʻchirilmaydi, holat faqat
  `draft → active → archived` yoʻnalishida oʻzgaradi (trigger);
- har bir mahsulotda bittadan ortiq faol va bittadan ortiq qoralama yoʻq (partial unique index);
- retsept faqat tayyor mahsulotga, tarkibida faqat xomashyo (kompozit FK `(id, kind)`);
- tayyor mahsulot doim dona, kod formati `XA-001` / `TM-001`, nomlar katta-kichik harfga qaramay takrorlanmas.

**Miqdorlar — BIGINT butun son** (gramm yoki dona). Float yoʻq. `int` emas, chunki
2,1 mlrd gramm atigi 2,1 tonna.

**Qulflash tartibi** (deadlock boʻlmasligi uchun hamma joyda bir xil):
tayyor mahsulot → retsept versiyasi → xomashyo qatorlari (id boʻyicha).
Admin rolini oʻzgartirishda avval barcha faol adminlar qulflanadi — ikki admin bir
vaqtda bir-birini bloklasa ham, bittasi qoladi.
`lock_timeout = 5s`: band qator cheksiz kutilmaydi, `409 LOCK_TIMEOUT` qaytadi.

**Mahsulotning `kind`, `unit`, `code`** yaratilgandan keyin oʻzgarmaydi — jurnal
tarixining maʼnosi shularga bogʻliq. Xato kiritilgan boʻlsa: arxivlab, yangisini yarating.

**Arxivlash cheklovlari:** qoldigʻi bor mahsulot (`PRODUCT_HAS_STOCK`) va faol retseptda
ishlatilayotgan xomashyo (`PRODUCT_USED_IN_ACTIVE_RECIPE`) arxivlanmaydi.

**Vaqt:** bazada `timestamptz` (UTC); "bugun", "7 kun" — `TIMEZONE` (Asia/Tashkent) boʻyicha.

**Loglar:** JSON, har qatorida `request_id` (javobda `X-Request-ID` sarlavhasi).

---

## Tekshiruv skriptlari

```bash
python -m scripts.check_ledger   # SUM(jurnal) = qoldiq; farq boʻlsa exit 1
```
