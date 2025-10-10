-- Create specialized memory tables for the new memory service architecture
-- Each memory type gets its own table with specific fields
-- Generated: 2025-07-15

SET search_path TO dev, public;

-- 1. Factual Memory Table
CREATE TABLE IF NOT EXISTS dev.factual_memories (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    fact_type TEXT NOT NULL DEFAULT 'general',
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_value TEXT NOT NULL,
    context JSONB DEFAULT '{}'::jsonb,
    confidence DOUBLE PRECISION DEFAULT 0.8,
    importance_score DOUBLE PRECISION DEFAULT 0.5,
    source TEXT,
    verification_status TEXT DEFAULT 'unverified',
    related_facts JSONB DEFAULT '[]'::jsonb,
    last_confirmed_at TIMESTAMP WITH TIME ZONE,
    embedding VECTOR(1536),
    tags JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Episodic Memory Table
CREATE TABLE IF NOT EXISTS dev.episodic_memories (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    event_type TEXT NOT NULL,
    episode_title TEXT,
    summary TEXT,
    location TEXT,
    participants JSONB DEFAULT '[]'::jsonb,
    key_events JSONB DEFAULT '[]'::jsonb,
    emotional_context TEXT DEFAULT 'neutral',
    emotional_intensity DOUBLE PRECISION DEFAULT 0.5,
    emotional_valence DOUBLE PRECISION DEFAULT 0.0,
    lessons_learned TEXT,
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    importance_score DOUBLE PRECISION DEFAULT 0.5,
    embedding VECTOR(1536),
    tags JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Semantic Memory Table
CREATE TABLE IF NOT EXISTS dev.semantic_memories (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    concept_type TEXT NOT NULL,
    concept_name TEXT NOT NULL,
    definition TEXT NOT NULL,
    concept_category TEXT NOT NULL DEFAULT 'general',
    properties JSONB DEFAULT '{}'::jsonb,
    related_concepts JSONB DEFAULT '[]'::jsonb,
    examples JSONB DEFAULT '[]'::jsonb,
    mastery_level DOUBLE PRECISION DEFAULT 0.0,
    learning_context TEXT,
    importance_score DOUBLE PRECISION DEFAULT 0.5,
    embedding VECTOR(1536),
    tags JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Procedural Memory Table
CREATE TABLE IF NOT EXISTS dev.procedural_memories (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    skill_type TEXT NOT NULL,
    procedure_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    prerequisites JSONB DEFAULT '[]'::jsonb,
    difficulty_level INTEGER DEFAULT 3,
    estimated_time_minutes INTEGER,
    success_rate DOUBLE PRECISION DEFAULT 0.0,
    usage_count INTEGER DEFAULT 0,
    expected_outcome TEXT,
    common_mistakes JSONB DEFAULT '[]'::jsonb,
    last_practiced_at TIMESTAMP WITH TIME ZONE,
    importance_score DOUBLE PRECISION DEFAULT 0.5,
    embedding VECTOR(1536),
    tags JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Working Memory Table
CREATE TABLE IF NOT EXISTS dev.working_memories (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    context_type TEXT NOT NULL,
    context_id TEXT NOT NULL,
    current_step TEXT,
    state_data JSONB DEFAULT '{}'::jsonb,
    task_context JSONB DEFAULT '{}'::jsonb,
    next_actions JSONB DEFAULT '[]'::jsonb,
    progress_percentage DOUBLE PRECISION DEFAULT 0.0,
    priority INTEGER DEFAULT 3,
    ttl_seconds INTEGER DEFAULT 3600,
    expires_at TIMESTAMP WITH TIME ZONE,
    importance_score DOUBLE PRECISION DEFAULT 0.5,
    embedding VECTOR(1536),
    tags JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Session Memory Table
CREATE TABLE IF NOT EXISTS dev.session_memories (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    conversation_summary TEXT,
    user_context JSONB DEFAULT '{}'::jsonb,
    key_decisions JSONB DEFAULT '[]'::jsonb,
    ongoing_tasks JSONB DEFAULT '[]'::jsonb,
    user_preferences JSONB DEFAULT '{}'::jsonb,
    important_facts JSONB DEFAULT '[]'::jsonb,
    total_messages INTEGER DEFAULT 0,
    interaction_sequence INTEGER DEFAULT 0,
    conversation_state JSONB DEFAULT '{}'::jsonb,
    importance_score DOUBLE PRECISION DEFAULT 0.5,
    embedding VECTOR(1536),
    tags JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. Memory Associations Table (for cross-memory relationships)
CREATE TABLE IF NOT EXISTS dev.memory_associations (
    id SERIAL PRIMARY KEY,
    source_memory_id TEXT NOT NULL,
    target_memory_id TEXT NOT NULL,
    association_type TEXT NOT NULL DEFAULT 'semantic_similarity',
    strength DOUBLE PRECISION DEFAULT 0.5,
    user_id TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 8. Memory Metadata Table (for analytics and performance tracking)
CREATE TABLE IF NOT EXISTS dev.memory_metadata (
    id SERIAL PRIMARY KEY,
    memory_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    user_id TEXT NOT NULL,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    accuracy_score DOUBLE PRECISION,
    relevance_score DOUBLE PRECISION,
    completeness_score DOUBLE PRECISION,
    decay_factor DOUBLE PRECISION DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 9. Memory Extraction Logs Table (for tracking intelligent processing)
CREATE TABLE IF NOT EXISTS dev.memory_extraction_logs (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    dialog_content TEXT NOT NULL,
    extraction_result JSONB DEFAULT '{}'::jsonb,
    success BOOLEAN DEFAULT FALSE,
    processing_time_ms INTEGER,
    error_message TEXT,
    confidence_score DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_factual_memories_user_id ON dev.factual_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_factual_memories_fact_type ON dev.factual_memories(fact_type);
CREATE INDEX IF NOT EXISTS idx_factual_memories_subject ON dev.factual_memories(subject);
CREATE INDEX IF NOT EXISTS idx_factual_memories_confidence ON dev.factual_memories(confidence);
CREATE INDEX IF NOT EXISTS idx_factual_memories_verification ON dev.factual_memories(verification_status);

CREATE INDEX IF NOT EXISTS idx_episodic_memories_user_id ON dev.episodic_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_episodic_memories_event_type ON dev.episodic_memories(event_type);
CREATE INDEX IF NOT EXISTS idx_episodic_memories_occurred_at ON dev.episodic_memories(occurred_at);
CREATE INDEX IF NOT EXISTS idx_episodic_memories_emotional_valence ON dev.episodic_memories(emotional_valence);

CREATE INDEX IF NOT EXISTS idx_semantic_memories_user_id ON dev.semantic_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_semantic_memories_category ON dev.semantic_memories(concept_category);
CREATE INDEX IF NOT EXISTS idx_semantic_memories_concept_type ON dev.semantic_memories(concept_type);
CREATE INDEX IF NOT EXISTS idx_semantic_memories_mastery ON dev.semantic_memories(mastery_level);

CREATE INDEX IF NOT EXISTS idx_procedural_memories_user_id ON dev.procedural_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_procedural_memories_domain ON dev.procedural_memories(domain);
CREATE INDEX IF NOT EXISTS idx_procedural_memories_skill_type ON dev.procedural_memories(skill_type);
CREATE INDEX IF NOT EXISTS idx_procedural_memories_difficulty ON dev.procedural_memories(difficulty_level);

CREATE INDEX IF NOT EXISTS idx_working_memories_user_id ON dev.working_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_working_memories_context_type ON dev.working_memories(context_type);
CREATE INDEX IF NOT EXISTS idx_working_memories_priority ON dev.working_memories(priority);
CREATE INDEX IF NOT EXISTS idx_working_memories_expires_at ON dev.working_memories(expires_at);
CREATE INDEX IF NOT EXISTS idx_working_memories_active ON dev.working_memories(is_active);

CREATE INDEX IF NOT EXISTS idx_session_memories_user_id ON dev.session_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_session_memories_session_id ON dev.session_memories(session_id);
CREATE INDEX IF NOT EXISTS idx_session_memories_active ON dev.session_memories(is_active);

CREATE INDEX IF NOT EXISTS idx_memory_associations_source ON dev.memory_associations(source_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_associations_target ON dev.memory_associations(target_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_associations_user_id ON dev.memory_associations(user_id);

CREATE INDEX IF NOT EXISTS idx_memory_metadata_memory_id ON dev.memory_metadata(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_metadata_user_id ON dev.memory_metadata(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_metadata_type ON dev.memory_metadata(memory_type);

CREATE INDEX IF NOT EXISTS idx_memory_extraction_logs_user_id ON dev.memory_extraction_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_extraction_logs_type ON dev.memory_extraction_logs(memory_type);
CREATE INDEX IF NOT EXISTS idx_memory_extraction_logs_created_at ON dev.memory_extraction_logs(created_at);

-- Vector similarity search indexes (using cosine distance)
CREATE INDEX IF NOT EXISTS idx_factual_memories_vector ON dev.factual_memories USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_episodic_memories_vector ON dev.episodic_memories USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_semantic_memories_vector ON dev.semantic_memories USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_procedural_memories_vector ON dev.procedural_memories USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_working_memories_vector ON dev.working_memories USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_session_memories_vector ON dev.session_memories USING ivfflat (embedding vector_cosine_ops);

-- Grant permissions for API access
GRANT USAGE ON SCHEMA dev TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA dev TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA dev TO anon, authenticated, service_role;

-- Add table comments
COMMENT ON TABLE dev.factual_memories IS 'Stores factual information in subject-predicate-object format with intelligent extraction from dialog';
COMMENT ON TABLE dev.episodic_memories IS 'Stores personal experiences and events with contextual and emotional information';
COMMENT ON TABLE dev.semantic_memories IS 'Stores conceptual knowledge, definitions, and semantic relationships';
COMMENT ON TABLE dev.procedural_memories IS 'Stores step-by-step procedures and how-to knowledge';
COMMENT ON TABLE dev.working_memories IS 'Stores temporary context and active task information with TTL';
COMMENT ON TABLE dev.session_memories IS 'Stores conversation summaries and session-specific context';
COMMENT ON TABLE dev.memory_associations IS 'Stores relationships and associations between different memories';
COMMENT ON TABLE dev.memory_metadata IS 'Stores analytics and performance tracking data for memories';
COMMENT ON TABLE dev.memory_extraction_logs IS 'Logs intelligent processing attempts for debugging and improvement';

RESET search_path;