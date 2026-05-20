CREATE TABLE IF NOT EXISTS accounts (
  account_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username   text NOT NULL UNIQUE,
  password   text NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  order_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id  uuid NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
  parent_asin text NOT NULL,
  quantity    integer NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
  id         bigserial PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
  role       text NOT NULL,          -- 'user' | 'assistant'
  content    text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
