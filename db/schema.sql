CREATE TABLE IF NOT EXISTS listings (
  id            TEXT PRIMARY KEY,
  url           TEXT,
  title         TEXT,
  price         INTEGER,
  currency      TEXT,
  rooms         INTEGER,
  area_sqm      REAL,
  floor         INTEGER,
  total_floors  INTEGER,
  district      TEXT,
  address       TEXT,
  description   TEXT,
  posted_at     TEXT,
  scraped_at    TEXT
);
CREATE TABLE IF NOT EXISTS photos (
  listing_id    TEXT,
  url           TEXT,
  local_path    TEXT,
  position      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price);
CREATE INDEX IF NOT EXISTS idx_listings_rooms ON listings(rooms);
CREATE INDEX IF NOT EXISTS idx_listings_area ON listings(area_sqm);
CREATE INDEX IF NOT EXISTS idx_listings_district ON listings(district);
CREATE INDEX IF NOT EXISTS idx_photos_listing ON photos(listing_id);
