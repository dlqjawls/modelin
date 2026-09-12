-- Foundation tables for the autonomous trading contracts.
-- Apply after reviewing ownership/RLS policies for the deployment environment.
create table if not exists v2_accounts (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references auth.users(id) on delete cascade,
  name varchar(100) not null,
  mode varchar(10) not null check (mode in ('paper','live')),
  broker varchar(50) not null,
  market varchar(10) not null check (market in ('krx','us','crypto')),
  currency varchar(10) not null,
  external_account_ref varchar(200),
  credential_ref varchar(200),
  created_at timestamptz not null default now()
);

create table if not exists v2_deployments (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references auth.users(id) on delete cascade,
  account_id uuid not null references v2_accounts(id) on delete restrict,
  strategy_spec jsonb not null,
  mode varchar(10) not null check (mode in ('paper','live')),
  allocation_amount numeric(38,18) not null check (allocation_amount > 0),
  allocation_currency varchar(10) not null,
  risk_policy jsonb not null default '{}',
  desired_state varchar(20) not null default 'DRAFT',
  observed_state varchar(20) not null default 'DRAFT',
  pause_epoch bigint not null default 0,
  revision bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists v2_one_active_deployment_per_account
  on v2_deployments(account_id) where observed_state not in ('ARCHIVED');

create table if not exists v2_strategy_runs (
  id uuid primary key default gen_random_uuid(),
  deployment_id uuid not null references v2_deployments(id) on delete restrict,
  schedule_key varchar(200) not null,
  decision jsonb not null,
  snapshot_id uuid,
  status varchar(20) not null default 'PLANNED',
  created_at timestamptz not null default now(),
  unique(deployment_id, schedule_key)
);

create table if not exists v2_order_intents (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references v2_strategy_runs(id) on delete restrict,
  account_id uuid not null references v2_accounts(id) on delete restrict,
  client_order_id varchar(128) not null,
  symbol varchar(50) not null,
  side varchar(4) not null check (side in ('buy','sell')),
  quantity numeric(38,18) not null check (quantity > 0),
  reference_price numeric(38,18) not null check (reference_price > 0),
  pause_epoch bigint not null,
  status varchar(20) not null default 'PENDING',
  created_at timestamptz not null default now(),
  unique(account_id, client_order_id),
  unique(run_id, symbol, side)
);

create table if not exists v2_orders (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references v2_accounts(id) on delete restrict,
  deployment_id uuid references v2_deployments(id) on delete restrict,
  client_order_id varchar(128) not null,
  broker_order_id varchar(200),
  symbol varchar(50) not null,
  side varchar(4) not null check (side in ('buy','sell')),
  quantity numeric(38,18),
  quote_amount numeric(38,18),
  lifecycle varchar(24) not null default 'CREATED',
  resolution varchar(16) not null default 'KNOWN',
  cancel_state varchar(16) not null default 'NONE',
  created_at timestamptz not null default now(),
  unique(account_id, client_order_id)
);

create table if not exists v2_fills (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references v2_orders(id) on delete restrict,
  account_id uuid not null references v2_accounts(id) on delete restrict,
  external_fill_id varchar(200) not null,
  quantity numeric(38,18) not null check (quantity > 0),
  price numeric(38,18) not null check (price > 0),
  fee_amount numeric(38,18) not null default 0,
  fee_currency varchar(10) not null,
  executed_at timestamptz not null,
  unique(account_id, external_fill_id)
);

create table if not exists v2_outbox (
  id bigint generated always as identity primary key,
  event_key varchar(200) not null unique,
  payload jsonb not null,
  status varchar(16) not null default 'PENDING',
  attempts integer not null default 0,
  next_attempt_at timestamptz not null default now(),
  lease_until timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists v2_account_leases (
  account_id uuid primary key references v2_accounts(id) on delete cascade,
  lease_owner varchar(200) not null,
  lease_until timestamptz not null,
  fencing_token bigint not null,
  updated_at timestamptz not null default now()
);

create table if not exists v2_api_requests (
  owner_scope varchar(200) not null,
  endpoint varchar(200) not null,
  idempotency_key varchar(200) not null,
  request_hash varchar(64) not null,
  status_code integer not null,
  response_json jsonb not null,
  created_at timestamptz not null default now(),
  primary key(owner_scope, endpoint, idempotency_key)
);
