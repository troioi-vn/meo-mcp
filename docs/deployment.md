# Deployment

`dev` deploys to `catarchy2` at `https://mcp-dev.meo-mai-moi.com`; `main` has no
deployment workflow. The runtime checkout is `/opt/meo-mcp-dev`, binds only to
`127.0.0.1:8020`, joins the external Docker network `shared-services`, and uses
database `meo_mcp_dev` through `shared-postgres`.

The server-managed `.env` contains `DATABASE_URL`, public and Meo URLs, the
Meo connector API key/HMAC secret, and a unique 32-byte base64url AES key. Do
not store it in Git. Back it up in Passbolt and expose CI values through OpenBao.

## Release path

1. Push a tested change to `dev`.
2. Woodpecker tests it, SSHes to the long-lived checkout, applies Alembic migrations,
   rebuilds Compose, and checks local and public health.
3. Roll back by deploying the preceding `dev` SHA. Migrations are additive; do not
   use a destructive downgrade during an incident.

## Future production (not provisioned)

Use `main`, `https://mcp.meo-mai-moi.com`, host `meo`, a distinct `meo_mcp`
database and credentials, and select a port only after a fresh host inventory.
