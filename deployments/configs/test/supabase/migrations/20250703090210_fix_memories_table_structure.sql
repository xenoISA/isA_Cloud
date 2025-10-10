-- Fix memories table structure to match code expectations
-- The current table has: content, importance_score, user_id
-- The code expects: key, value, category, importance, created_by

SET search_path TO dev, public;

-- Add missing columns to match code expectations
ALTER TABLE dev.memories 
ADD COLUMN IF NOT EXISTS key TEXT,
ADD COLUMN IF NOT EXISTS value TEXT,
ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'general',
ADD COLUMN IF NOT EXISTS importance INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS created_by TEXT DEFAULT 'default',
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Create unique constraint on key (since the code expects it to be unique)
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_key ON dev.memories(key);

-- Migrate existing data if any exists
-- Map content -> value, importance_score -> importance, user_id -> created_by
UPDATE dev.memories 
SET 
    value = content,
    importance = COALESCE(ROUND(importance_score * 10)::INTEGER, 1), -- Convert 0-1 score to 1-10 scale
    created_by = COALESCE(user_id::TEXT, 'default'),
    updated_at = COALESCE(created_at, NOW()),
    key = 'migrated_' || id::TEXT  -- Generate keys for existing records
WHERE key IS NULL;

-- Make legacy content field nullable since we now use value field
ALTER TABLE dev.memories ALTER COLUMN content DROP NOT NULL;

-- Add NOT NULL constraints after data migration
ALTER TABLE dev.memories 
ALTER COLUMN key SET NOT NULL,
ALTER COLUMN value SET NOT NULL;

-- Add index for better performance
CREATE INDEX IF NOT EXISTS idx_memories_category ON dev.memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON dev.memories(importance);
CREATE INDEX IF NOT EXISTS idx_memories_created_by ON dev.memories(created_by);

-- Grant permissions for API access
GRANT USAGE ON SCHEMA dev TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA dev TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA dev TO anon, authenticated, service_role;

-- Add comment
COMMENT ON TABLE dev.memories IS 'Memory storage for MCP server with both new and legacy column support';

RESET search_path;