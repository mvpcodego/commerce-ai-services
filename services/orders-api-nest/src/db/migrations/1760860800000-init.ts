import type { MigrationInterface, QueryRunner } from "typeorm"

export class Init1760860800000 implements MigrationInterface {
  name = "Init1760860800000"

  async up(q: QueryRunner): Promise<void> {
    await q.query(`
      CREATE TABLE cars (
        id int PRIMARY KEY,
        make text NOT NULL,
        model text NOT NULL,
        generation text,
        year_from int,
        year_to int,
        slug text NOT NULL UNIQUE
      );
      CREATE TABLE parts (
        id int PRIMARY KEY,
        sku text NOT NULL UNIQUE,
        type text NOT NULL,
        title text NOT NULL,
        brand text,
        specs jsonb NOT NULL DEFAULT '{}',
        price_kopecks int NOT NULL CHECK (price_kopecks >= 0),
        stock int NOT NULL DEFAULT 0,
        archived boolean NOT NULL DEFAULT false,
        image_url text
      );
      CREATE INDEX parts_type_idx ON parts (type);
      CREATE TABLE kits (
        id int PRIMARY KEY,
        sku text NOT NULL UNIQUE,
        car_id int NOT NULL REFERENCES cars (id),
        head_unit_id int NOT NULL REFERENCES parts (id),
        frame_id int NOT NULL REFERENCES parts (id),
        wiring_id int NOT NULL REFERENCES parts (id),
        starter_kit_id int REFERENCES parts (id),
        title text NOT NULL,
        price_kopecks int NOT NULL CHECK (price_kopecks >= 0),
        is_default boolean NOT NULL DEFAULT false
      );
      CREATE INDEX kits_car_idx ON kits (car_id);

      CREATE TABLE orders (
        id serial PRIMARY KEY,
        status text NOT NULL CHECK (status IN ('new', 'confirmed', 'shipped', 'delivered', 'cancelled')),
        customer_name text NOT NULL,
        customer_phone text NOT NULL,
        customer_city text,
        total_kopecks bigint NOT NULL CHECK (total_kopecks >= 0),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
      );
      CREATE INDEX orders_status_created_idx ON orders (status, created_at DESC, id DESC);
      CREATE INDEX orders_created_idx ON orders (created_at DESC, id DESC);
      CREATE TABLE order_items (
        id serial PRIMARY KEY,
        order_id int NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
        position int NOT NULL,
        sku text NOT NULL,
        title text NOT NULL,
        unit_price_kopecks int NOT NULL CHECK (unit_price_kopecks >= 0),
        quantity int NOT NULL CHECK (quantity > 0),
        line_total_kopecks bigint NOT NULL,
        UNIQUE (order_id, position)
      );

      CREATE TABLE idempotency_keys (
        key text PRIMARY KEY,
        request_hash text NOT NULL,
        order_id int REFERENCES orders (id),
        response jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
      );

      CREATE TABLE outbox (
        id bigserial PRIMARY KEY,
        event_id uuid NOT NULL UNIQUE,
        topic text NOT NULL,
        message_key text NOT NULL,
        payload jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        available_at timestamptz NOT NULL DEFAULT now(),
        published_at timestamptz,
        attempts int NOT NULL DEFAULT 0,
        last_error text
      );
      -- Релей выбирает только неопубликованные: частичный индекс остаётся маленьким.
      CREATE INDEX outbox_pending_idx ON outbox (available_at, id) WHERE published_at IS NULL;
    `)
  }

  async down(q: QueryRunner): Promise<void> {
    await q.query(`DROP TABLE outbox, idempotency_keys, order_items, orders, kits, parts, cars`)
  }
}
