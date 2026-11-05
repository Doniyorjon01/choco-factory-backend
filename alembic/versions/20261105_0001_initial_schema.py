"""initial schema

Barcha jadvallar, cheklovlar va o'zgarmaslik triggerlari:
- documents, ledger_entries, production_recipe_snapshot — faqat INSERT;
- faol/arxiv retsept versiyasining tarkibi o'zgarmaydi va versiya o'chirilmaydi.

Revision ID: 0001
Revises:
Create Date: 2026-11-05 02:21:59.603619
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


IMMUTABLE_TABLES = ("documents", "ledger_entries", "production_recipe_snapshot")

IMMUTABLE_FN = """
CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% on % is forbidden: the ledger is append-only, use a reversal document',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$;
"""

# Kaskad o'chirishda ota-versiya allaqachon o'chgan bo'ladi (status NULL) —
# bu faqat qoralamani o'chirishda yuz beradi, shuning uchun ruxsat.
RECIPE_LINES_FN = """
CREATE FUNCTION recipe_lines_draft_only() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_status text;
BEGIN
    SELECT status INTO v_status FROM recipe_versions
     WHERE id = COALESCE(NEW.recipe_version_id, OLD.recipe_version_id);
    IF v_status IS NOT NULL AND v_status <> 'draft' THEN
        RAISE EXCEPTION 'recipe version % is %, its lines are immutable',
            COALESCE(NEW.recipe_version_id, OLD.recipe_version_id), v_status
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.recipe_version_id <> OLD.recipe_version_id THEN
        RAISE EXCEPTION 'recipe line cannot move between versions'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;
"""

# Ruxsat etilgan o'tishlar: draft -> active, active -> archived.
# Faol yoki arxiv versiya o'chirilmaydi; mahsulot va raqam o'zgarmaydi.
RECIPE_VERSIONS_FN = """
CREATE FUNCTION recipe_versions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'draft' THEN
            RAISE EXCEPTION 'recipe version % is %, it cannot be deleted', OLD.id, OLD.status
                USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN OLD;
    END IF;
    IF NEW.product_id <> OLD.product_id OR NEW.version <> OLD.version THEN
        RAISE EXCEPTION 'recipe version identity is immutable'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.status <> OLD.status AND NOT (
        (OLD.status = 'draft' AND NEW.status = 'active') OR
        (OLD.status = 'active' AND NEW.status = 'archived')
    ) THEN
        RAISE EXCEPTION 'recipe status % -> % is not allowed', OLD.status, NEW.status
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.status <> 'draft' AND NEW.note IS DISTINCT FROM OLD.note THEN
        RAISE EXCEPTION 'note of a non-draft recipe version is immutable'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""


def upgrade() -> None:
    op.create_table(
        "doc_counters",
        sa.Column("doc_type", sa.String(length=16), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint("last_number >= 0", name=op.f("ck_doc_counters_last_number_nonnegative")),
        sa.PrimaryKeyConstraint("doc_type", name=op.f("pk_doc_counters")),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name_uz", sa.String(length=150), nullable=False),
        sa.Column("name_ru", sa.String(length=150), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("unit", sa.String(length=4), nullable=False),
        sa.Column("min_qty", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("target_qty", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(kind = 'raw' AND code ~ '^XA-[0-9]{3,}$') OR (kind = 'finished' AND code ~ '^TM-[0-9]{3,}$')",
            name=op.f("ck_products_code_format"),
        ),
        sa.CheckConstraint("kind = 'raw' OR unit = 'pcs'", name=op.f("ck_products_finished_in_pcs")),
        sa.CheckConstraint("kind IN ('raw', 'finished')", name=op.f("ck_products_kind_valid")),
        sa.CheckConstraint("unit IN ('g', 'pcs')", name=op.f("ck_products_unit_valid")),
        sa.CheckConstraint("is_archived = (archived_at IS NOT NULL)", name=op.f("ck_products_archived_at_consistent")),
        sa.CheckConstraint(
            "length(trim(name_uz)) > 0 AND length(trim(name_ru)) > 0", name=op.f("ck_products_names_not_blank")
        ),
        sa.CheckConstraint("min_qty >= 0", name=op.f("ck_products_min_qty_nonnegative")),
        sa.CheckConstraint("target_qty >= min_qty", name=op.f("ck_products_target_gte_min")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("code", name=op.f("uq_products_code")),
        sa.UniqueConstraint("id", "kind", name="uq_products_id_kind"),
    )
    op.create_index("ix_products_kind_archived", "products", ["kind", "is_archived"], unique=False)
    op.create_index("uq_products_name_ru_lower", "products", [sa.literal_column("lower(name_ru)")], unique=True)
    op.create_index("uq_products_name_uz_lower", "products", [sa.literal_column("lower(name_uz)")], unique=True)
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("login", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("token_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lang", sa.String(length=2), server_default=sa.text("'uz'"), nullable=False),
        sa.Column("created_by_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("lang IN ('uz', 'ru')", name=op.f("ck_users_lang_valid")),
        sa.CheckConstraint("role IN ('admin', 'warehouse', 'operator')", name=op.f("ck_users_role_valid")),
        sa.CheckConstraint("failed_login_count >= 0", name=op.f("ck_users_failed_login_count_nonnegative")),
        sa.CheckConstraint("login = lower(login)", name=op.f("ck_users_login_lowercase")),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name=op.f("fk_users_created_by_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("login", name=op.f("uq_users_login")),
    )
    op.create_table(
        "recipe_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("product_kind", sa.String(length=10), server_default=sa.text("'finished'"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "(status = 'draft') = (activated_at IS NULL AND activated_by_id IS NULL)",
            name=op.f("ck_recipe_versions_activation_consistent"),
        ),
        sa.CheckConstraint("product_kind = 'finished'", name=op.f("ck_recipe_versions_product_is_finished")),
        sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name=op.f("ck_recipe_versions_status_valid")),
        sa.CheckConstraint("version > 0", name=op.f("ck_recipe_versions_version_positive")),
        sa.ForeignKeyConstraint(
            ["activated_by_id"], ["users.id"], name=op.f("fk_recipe_versions_activated_by_id_users")
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name=op.f("fk_recipe_versions_created_by_id_users")),
        sa.ForeignKeyConstraint(
            ["product_id", "product_kind"], ["products.id", "products.kind"], name="fk_recipe_versions_product_finished"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_versions")),
        sa.UniqueConstraint("product_id", "version", name="uq_recipe_versions_product_id_version"),
    )
    op.create_index(
        "uq_recipe_versions_one_active",
        "recipe_versions",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_recipe_versions_one_draft",
        "recipe_versions",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_table(
        "stock_balance",
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("qty", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("qty >= 0", name=op.f("ck_stock_balance_qty_nonnegative")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_stock_balance_product_id_products")),
        sa.PrimaryKeyConstraint("product_id", name=op.f("pk_stock_balance")),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("doc_type", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("quantity", sa.BigInteger(), nullable=True),
        sa.Column("recipe_version_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("reverses_id", sa.BigInteger(), nullable=True),
        sa.Column("supplier_name", sa.String(length=200), nullable=True),
        sa.Column("supplier_doc_no", sa.String(length=64), nullable=True),
        sa.Column("supplier_doc_date", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "(doc_type = 'reversal') = (reverses_id IS NOT NULL)", name=op.f("ck_documents_reversal_has_target")
        ),
        sa.CheckConstraint(
            "doc_type <> 'production' OR (product_id IS NOT NULL AND quantity > 0 AND recipe_version_id IS NOT NULL)",
            name=op.f("ck_documents_production_fields"),
        ),
        sa.CheckConstraint(
            "doc_type = 'receipt' OR (supplier_name IS NULL AND supplier_doc_no IS NULL AND supplier_doc_date IS NULL)",
            name=op.f("ck_documents_supplier_only_on_receipt"),
        ),
        sa.CheckConstraint(
            "doc_type IN ('receipt', 'production', 'adjustment', 'scrap', 'reversal')",
            name=op.f("ck_documents_doc_type_valid"),
        ),
        sa.CheckConstraint(
            "doc_type NOT IN ('adjustment', 'scrap') OR (product_id IS NOT NULL AND quantity IS NOT NULL)",
            name=op.f("ck_documents_single_product_fields"),
        ),
        sa.CheckConstraint(
            "doc_type NOT IN ('adjustment', 'scrap', 'reversal') OR reason IS NOT NULL",
            name=op.f("ck_documents_reason_required"),
        ),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name=op.f("ck_documents_quantity_nonnegative")),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name=op.f("fk_documents_created_by_id_users")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_documents_product_id_products")),
        sa.ForeignKeyConstraint(
            ["recipe_version_id"], ["recipe_versions.id"], name=op.f("fk_documents_recipe_version_id_recipe_versions")
        ),
        sa.ForeignKeyConstraint(["reverses_id"], ["documents.id"], name=op.f("fk_documents_reverses_id_documents")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("number", name=op.f("uq_documents_number")),
        sa.UniqueConstraint("request_id", name=op.f("uq_documents_request_id")),
        sa.UniqueConstraint("reverses_id", name=op.f("uq_documents_reverses_id")),
    )
    op.create_index("ix_documents_created_at", "documents", ["created_at"], unique=False)
    op.create_index("ix_documents_created_by_created", "documents", ["created_by_id", "created_at"], unique=False)
    op.create_index("ix_documents_product_id", "documents", ["product_id"], unique=False)
    op.create_index("ix_documents_type_created", "documents", ["doc_type", "created_at"], unique=False)
    op.create_table(
        "recipe_lines",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("recipe_version_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_product_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_kind", sa.String(length=10), server_default=sa.text("'raw'"), nullable=False),
        sa.Column("qty_per_unit", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("raw_kind = 'raw'", name=op.f("ck_recipe_lines_product_is_raw")),
        sa.CheckConstraint("qty_per_unit > 0", name=op.f("ck_recipe_lines_qty_per_unit_positive")),
        sa.ForeignKeyConstraint(
            ["raw_product_id", "raw_kind"], ["products.id", "products.kind"], name="fk_recipe_lines_raw_product"
        ),
        sa.ForeignKeyConstraint(
            ["recipe_version_id"],
            ["recipe_versions.id"],
            name=op.f("fk_recipe_lines_recipe_version_id_recipe_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_lines")),
        sa.UniqueConstraint("recipe_version_id", "raw_product_id", name="uq_recipe_lines_version_raw"),
    )
    op.create_index(op.f("ix_recipe_lines_raw_product_id"), "recipe_lines", ["raw_product_id"], unique=False)
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("qty_delta", sa.BigInteger(), nullable=False),
        sa.Column("qty_after", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("qty_after >= 0", name=op.f("ck_ledger_entries_qty_after_nonnegative")),
        sa.CheckConstraint("qty_delta <> 0", name=op.f("ck_ledger_entries_qty_delta_nonzero")),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name=op.f("fk_ledger_entries_document_id_documents")
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_ledger_entries_product_id_products")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_entries")),
        sa.UniqueConstraint("document_id", "product_id", name="uq_ledger_entries_document_product"),
    )
    op.create_index("ix_ledger_entries_product_created", "ledger_entries", ["product_id", "created_at"], unique=False)
    op.create_table(
        "production_recipe_snapshot",
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_product_id", sa.BigInteger(), nullable=False),
        sa.Column("qty_per_unit", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("qty_per_unit > 0", name=op.f("ck_production_recipe_snapshot_qty_per_unit_positive")),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name=op.f("fk_production_recipe_snapshot_document_id_documents")
        ),
        sa.ForeignKeyConstraint(
            ["raw_product_id"], ["products.id"], name=op.f("fk_production_recipe_snapshot_raw_product_id_products")
        ),
        sa.PrimaryKeyConstraint("document_id", "raw_product_id", name=op.f("pk_production_recipe_snapshot")),
    )

    # Hujjat raqamlari hisoblagichlari (uzluksiz raqamlash)
    op.execute(
        "INSERT INTO doc_counters (doc_type, last_number) VALUES "
        "('receipt', 0), ('production', 0), ('adjustment', 0), ('scrap', 0), ('reversal', 0)"
    )

    # --- Jurnal o'zgarmasligi: hujjat va harakatlar faqat qo'shiladi ---
    op.execute(IMMUTABLE_FN)
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()"
        )

    # --- Retsept: faqat qoralama tahrirlanadi va o'chiriladi ---
    op.execute(RECIPE_LINES_FN)
    op.execute(
        "CREATE TRIGGER trg_recipe_lines_draft_only BEFORE INSERT OR UPDATE OR DELETE ON recipe_lines "
        "FOR EACH ROW EXECUTE FUNCTION recipe_lines_draft_only()"
    )
    op.execute(RECIPE_VERSIONS_FN)
    op.execute(
        "CREATE TRIGGER trg_recipe_versions_guard BEFORE UPDATE OR DELETE ON recipe_versions "
        "FOR EACH ROW EXECUTE FUNCTION recipe_versions_guard()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_recipe_versions_guard ON recipe_versions")
    op.execute("DROP TRIGGER IF EXISTS trg_recipe_lines_draft_only ON recipe_lines")
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_truncate ON {table}")
    op.execute("DROP FUNCTION IF EXISTS recipe_versions_guard()")
    op.execute("DROP FUNCTION IF EXISTS recipe_lines_draft_only()")
    op.execute("DROP FUNCTION IF EXISTS forbid_mutation()")
    op.drop_table("production_recipe_snapshot")
    op.drop_index("ix_ledger_entries_product_created", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index(op.f("ix_recipe_lines_raw_product_id"), table_name="recipe_lines")
    op.drop_table("recipe_lines")
    op.drop_index("ix_documents_type_created", table_name="documents")
    op.drop_index("ix_documents_product_id", table_name="documents")
    op.drop_index("ix_documents_created_by_created", table_name="documents")
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_table("documents")
    op.drop_table("stock_balance")
    op.drop_index(
        "uq_recipe_versions_one_draft", table_name="recipe_versions", postgresql_where=sa.text("status = 'draft'")
    )
    op.drop_index(
        "uq_recipe_versions_one_active", table_name="recipe_versions", postgresql_where=sa.text("status = 'active'")
    )
    op.drop_table("recipe_versions")
    op.drop_table("users")
    op.drop_index("uq_products_name_uz_lower", table_name="products")
    op.drop_index("uq_products_name_ru_lower", table_name="products")
    op.drop_index("ix_products_kind_archived", table_name="products")
    op.drop_table("products")
    op.drop_table("doc_counters")
