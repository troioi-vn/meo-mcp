"""initial oauth persistence

Revision ID: 20260717_0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260717_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table("oauth_clients", sa.Column("id", uuid, primary_key=True), sa.Column("client_id", sa.String(255), nullable=False), sa.Column("metadata", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("client_id"))
    op.create_index("ix_oauth_clients_client_id", "oauth_clients", ["client_id"])
    op.create_table("authorization_requests", sa.Column("id", uuid, primary_key=True), sa.Column("client_id", sa.String(255), nullable=False), sa.Column("redirect_uri", sa.Text(), nullable=False), sa.Column("redirect_uri_explicit", sa.Boolean(), nullable=False), sa.Column("state", sa.Text()), sa.Column("scopes", sa.JSON(), nullable=False), sa.Column("code_challenge", sa.String(255), nullable=False), sa.Column("resource", sa.Text(), nullable=False), sa.Column("client_name", sa.String(100), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("consumed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_authorization_requests_expires_at", "authorization_requests", ["expires_at"])
    op.create_index("ix_authorization_requests_client_id", "authorization_requests", ["client_id"])
    op.create_table("grants", sa.Column("id", uuid, primary_key=True), sa.Column("client_id", sa.String(255), nullable=False), sa.Column("subject", sa.String(255), nullable=False), sa.Column("scopes", sa.JSON(), nullable=False), sa.Column("delegated_token_ciphertext", sa.Text(), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True)), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_grants_client_id", "grants", ["client_id"]); op.create_index("ix_grants_subject", "grants", ["subject"])
    for name, cols in {"authorization_codes": [sa.Column("code_hash", sa.String(64), nullable=False), sa.Column("grant_id", uuid, sa.ForeignKey("grants.id"), nullable=False), sa.Column("client_id", sa.String(255), nullable=False), sa.Column("scopes", sa.JSON(), nullable=False), sa.Column("code_challenge", sa.String(255), nullable=False), sa.Column("redirect_uri", sa.Text(), nullable=False), sa.Column("redirect_uri_explicit", sa.Boolean(), nullable=False), sa.Column("resource", sa.Text(), nullable=False), sa.Column("subject", sa.String(255), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("consumed_at", sa.DateTime(timezone=True))], "access_tokens": [sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("grant_id", uuid, sa.ForeignKey("grants.id"), nullable=False), sa.Column("client_id", sa.String(255), nullable=False), sa.Column("scopes", sa.JSON(), nullable=False), sa.Column("subject", sa.String(255), nullable=False), sa.Column("resource", sa.Text(), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True))], "refresh_tokens": [sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("family_id", uuid, nullable=False), sa.Column("grant_id", uuid, sa.ForeignKey("grants.id"), nullable=False), sa.Column("client_id", sa.String(255), nullable=False), sa.Column("scopes", sa.JSON(), nullable=False), sa.Column("subject", sa.String(255), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("consumed_at", sa.DateTime(timezone=True)), sa.Column("revoked_at", sa.DateTime(timezone=True))]}.items():
        op.create_table(name, sa.Column("id", uuid, primary_key=True), *cols)
        hash_column = "code_hash" if name == "authorization_codes" else "token_hash"
        op.create_index(f"ix_{name}_{hash_column}", name, [hash_column], unique=True)
        op.create_index(f"ix_{name}_grant_id", name, ["grant_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_client_id", "refresh_tokens", ["client_id"])
    op.create_index("ix_access_tokens_client_id", "access_tokens", ["client_id"])
    op.create_index("ix_access_tokens_expires_at", "access_tokens", ["expires_at"])

def downgrade():
    op.drop_table("refresh_tokens"); op.drop_table("access_tokens"); op.drop_table("authorization_codes"); op.drop_table("grants"); op.drop_table("authorization_requests"); op.drop_table("oauth_clients")
