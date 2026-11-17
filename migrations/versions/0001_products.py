"""Create product inventory and maintain its update timestamp."""
from alembic import op
import sqlalchemy as sa

revision = "0001_products"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "products",
        sa.Column("sku", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price_eur", sa.Numeric(10, 2), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_products_name"),
        sa.CheckConstraint("price_eur >= 0 AND price_eur <> 'NaN'::numeric", name="ck_products_price"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_products_stock"),
    )
    op.execute("""
        CREATE FUNCTION touch_product() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = statement_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER products_updated BEFORE UPDATE ON products
        FOR EACH ROW EXECUTE FUNCTION touch_product()
    """)


def downgrade():
    op.drop_table("products")
    op.execute("DROP FUNCTION touch_product()")
