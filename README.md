# RetailOps AI · Live Product Inventory API

Milestone 1 gives your n8n support agent one read-only tool. Given a SKU, it can answer questions about current price and stock.

```text
n8n Cloud ── HTTPS + X-API-Key ──> Railway / FastAPI ── private connection ──> PostgreSQL
```

## Follow one request

For `GET /products/HP-001`, FastAPI checks the header before opening a database connection. SQLAlchemy builds a parameterized query, and psycopg sends it to PostgreSQL. Each lookup reads the current committed row. Pydantic turns the decimal price into a two-place string so that n8n receives this exact shape for the initial Sony record.

```json
{"sku":"HP-001","name":"Sony WH-1000XM5","stock_quantity":8,"price_eur":"299.00","currency":"EUR","data_source":"POSTGRESQL_DEMO"}
```

| Request | What it tells you |
| --- | --- |
| `GET /health` | The web process can answer. Returns 200 even during a database outage. |
| `GET /ready` | The API can run a database query. Returns 200 or 503. |
| `GET /products/{sku}` | Exact, case-sensitive SKU lookup. Returns 200, 401 for a missing or incorrect key, 404 for an unknown SKU, or 503 on a database error. |

PostgreSQL enforces required fields, unique SKUs, and nonnegative stock and prices for every writer. A database trigger keeps the timezone-aware `updated_at` current after an edit. The seed inserts the three demo rows in one transaction. On a primary-key conflict it skips that SKU, preserving all edits. Application startup only reads configuration.

## Run locally on Windows

Use PowerShell in the directory containing this README. Install Python 3.12 or newer and start Docker Desktop in Linux container mode. These commands use the Windows Python launcher and call the virtual environment’s interpreter directly.

```powershell
py -3 -m venv .venv
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -r requirements-dev.txt
```

Run this next block once for a fresh local database. It generates credentials in the ignored `.env` file and starts PostgreSQL on your machine’s loopback interface. Keep the file for subsequent sessions.

```powershell
if (Test-Path .env) { throw "Existing .env found. Reuse it or choose a fresh project directory." }
$env:POSTGRES_PASSWORD = & $py -c "import secrets; print(secrets.token_hex(24))"
$key = & $py -c "import secrets; print(secrets.token_urlsafe(32))"
(Get-Content .env.example) -replace 'REPLACE_LOCAL_PASSWORD', $env:POSTGRES_PASSWORD -replace '^API_KEY=$', "API_KEY=$key" | Set-Content -Encoding ascii .env
docker run --name retailops-pg -e POSTGRES_USER=inventory -e POSTGRES_PASSWORD -e POSTGRES_DB=inventory -p 127.0.0.1:5432:5432 -v retailops-pgdata:/var/lib/postgresql/data -d postgres:16
Remove-Item Env:POSTGRES_PASSWORD
docker exec retailops-pg pg_isready -U inventory -d inventory
```

Once the probe says `accepting connections`, create the tables, seed the database and start the web server.

```powershell
& $py -m alembic upgrade head
& $py -m inventory.seed
& $py -m uvicorn inventory.api:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

In a second PowerShell window in the same directory, try all three endpoints.

```powershell
$key = ((Get-Content .env | Where-Object { $_ -match '^API_KEY=' }) -split '=', 2)[1]
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8000/products/HP-001 -Headers @{'X-API-Key'=$key} | ConvertTo-Json
```

To see what “live” means, change one stock count through the local database, rerun the seed, and repeat the HTTP request. It should return 7. You can restore 8 with the same SQL command.

```powershell
docker exec retailops-pg psql -U inventory -d inventory -c "UPDATE products SET stock_quantity=7 WHERE sku='HP-001';"
.\.venv\Scripts\python.exe -m inventory.seed
```

Press Ctrl+C in the server window to stop FastAPI. Use `docker stop retailops-pg` and `docker start retailops-pg` to pause and resume the database. To restart FastAPI in a new shell, run the Uvicorn command using `.\.venv\Scripts\python.exe` in place of `& $py`.

## Run the tests

Create the test database once, then run pytest from the repository root. Each database test migrates and seeds a fresh temporary schema in `TEST_DATABASE_URL` and removes that schema afterward. The outage test reserves a loopback port with no database listening on it.

```powershell
docker exec retailops-pg createdb -U inventory inventory_test
.\.venv\Scripts\python.exe -m pytest -q
```

## Publish to GitHub and deploy on Railway

Install Git, GitHub CLI (`gh`), and Railway CLI (`railway`). From this local Git checkout, sign in to the GitHub account that should own the private repository. If you copied the files without Git history, run `git init -b main`, `git add .`, and `git commit -m "Build inventory API"` first.

```powershell
gh auth login
gh repo create retailops-inventory --private --source=. --remote=origin --push
railway login
railway init --name retailops-inventory
railway add --database postgres
railway open
```

In the Railway project, open the **Postgres** service’s **Settings → Networking**. Remove any public TCP proxy created by the database template and leave private networking enabled. Use the default database service name `Postgres` in the reference below. [Railway private networking](https://docs.railway.com/networking/private-networking)

Create the API service, set its private database reference, and deploy the committed source. The single quotes around the database reference are significant in PowerShell. These commands retain the new cloud key in memory so you can put it in n8n.

```powershell
railway add --service api
railway variable set 'DATABASE_URL=${{Postgres.DATABASE_URL}}' --service api --skip-deploys
$cloudKey = py -3 -c "import secrets; print(secrets.token_urlsafe(32))"
railway variable set "API_KEY=$cloudKey" --service api --skip-deploys
railway up --service api
railway domain --service api
```

The Dockerfile runs Uvicorn on `0.0.0.0` using Railway’s `PORT`. Before rollout, Railway runs Alembic and the seed against the private database. It checks `/ready` before routing traffic. For subsequent releases, push your commit to GitHub and rerun `railway up --service api` from that checkout. [Railway pre-deploy commands](https://docs.railway.com/deployments/pre-deploy-command) · [Railway variables](https://docs.railway.com/cli/variable)

Paste the HTTPS origin printed by the domain command when prompted.

```powershell
$origin = (Read-Host "Railway HTTPS origin").TrimEnd('/')
Invoke-RestMethod "$origin/ready"
Invoke-RestMethod "$origin/products/HP-002" -Headers @{'X-API-Key'=$cloudKey} | ConvertTo-Json
```

Expect the JBL headphones with stock 0. Keep the production key in your password manager or Railway’s service variables. The application does not log credentials or SQL parameters.

## Connect your n8n Cloud agent

1. Add an **HTTP Request Tool** to your AI Agent. Name it `lookup_product` and describe its input as an exact inventory SKU.
2. Select **GET**. Set the URL field to **Expression**. Replace `YOUR-DOMAIN` below with the Railway API hostname. Only the SKU comes from the agent.
3. Under **Authentication**, choose **Generic Credential Type → Header Auth**. Create a credential with Name `X-API-Key` and the production API key as Value. In the deployment shell, `Set-Clipboard -Value $cloudKey` lets you paste the key into the credential. Clear the clipboard afterward.
4. Ask the agent for the stock of `HP-002`. Tell it to report the returned count on success, treat 404 as an unknown SKU, and say the inventory lookup is unavailable on 401 or 503. Once the lookup works, remove the hard-coded lookup from the workflow.

```javascript
{{ 'https://YOUR-DOMAIN/products/' + encodeURIComponent($fromAI('sku', 'Exact product SKU such as HP-001', 'string')) }}
```

If you use an ordinary HTTP Request node with an incoming `sku` field, replace the `$fromAI(...)` call with `$json.sku`. [n8n HTTP Request credentials](https://docs.n8n.io/integrations/builtin/credentials/httprequest/)
