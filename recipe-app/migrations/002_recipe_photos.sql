-- Optional cover photo; originals are never exposed or retained.
ALTER TABLE recipes ADD COLUMN photo_key VARCHAR(32) UNIQUE
    CHECK (photo_key IS NULL OR photo_key ~ '^[0-9a-f]{32}$');
