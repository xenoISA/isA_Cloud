-- MCP Service Database Schema
-- Based on production database structure with 30 tables
-- Generated: 2025-07-02

-- RLS will be enabled per table as needed

-- Set search_path to use dev schema by default
SET search_path TO dev, public;

-- 1. Users and Authentication
CREATE TABLE dev.users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE dev.user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dev.users(id) ON DELETE CASCADE,
    session_token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE dev.user_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dev.users(id) ON DELETE CASCADE,
    preferences JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Services and Capabilities
CREATE TABLE dev.services (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    endpoint TEXT,
    status TEXT DEFAULT 'active',
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE dev.service_capabilities (
    id SERIAL PRIMARY KEY,
    service_id INTEGER REFERENCES dev.services(id) ON DELETE CASCADE,
    capability_name TEXT NOT NULL,
    capability_type TEXT NOT NULL,
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE dev.service_health (
    id SERIAL PRIMARY KEY,
    service_id INTEGER REFERENCES dev.services(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    response_time DOUBLE PRECISION,
    error_message TEXT,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE dev.service_metrics (
    id SERIAL PRIMARY KEY,
    service_id INTEGER REFERENCES dev.services(id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Core MCP Tables
CREATE TABLE dev.tool_embeddings (
    id SERIAL PRIMARY KEY,
    tool_name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    keywords TEXT[],
    embedding VECTOR(1536), -- OpenAI embedding dimension
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE dev.tool_selections (
    id SERIAL PRIMARY KEY,
    user_request TEXT NOT NULL,
    selected_tools JSONB NOT NULL,
    similarities JSONB,
    confidence_score DOUBLE PRECISION,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id INTEGER REFERENCES dev.users(id)
);

CREATE TABLE dev.prompt_embeddings (
    id SERIAL PRIMARY KEY,
    prompt_name TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    embedding VECTOR(1536),
    category TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE dev.resource_embeddings (
    id SERIAL PRIMARY KEY,
    resource_name TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_uri TEXT,
    description TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Tracing and Monitoring
CREATE TABLE dev.traces (
    id SERIAL PRIMARY KEY,
    trace_id TEXT UNIQUE NOT NULL,
    operation_name TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    start_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    end_time TIMESTAMP WITH TIME ZONE,
    duration DOUBLE PRECISION,
    user_id INTEGER REFERENCES dev.users(id),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE dev.spans (
    id SERIAL PRIMARY KEY,
    span_id TEXT UNIQUE NOT NULL,
    trace_id TEXT REFERENCES dev.traces(trace_id) ON DELETE CASCADE,
    parent_span_id TEXT,
    operation_name TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    start_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    end_time TIMESTAMP WITH TIME ZONE,
    duration DOUBLE PRECISION,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE dev.span_logs (
    id SERIAL PRIMARY KEY,
    span_id TEXT REFERENCES dev.spans(span_id) ON DELETE CASCADE,
    level TEXT NOT NULL, -- debug, info, warn, error
    message TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE dev.langgraph_executions (
    id SERIAL PRIMARY KEY,
    trace_id TEXT REFERENCES dev.traces(trace_id) ON DELETE CASCADE,
    span_id TEXT REFERENCES dev.spans(span_id) ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    execution_order INTEGER,
    input_state JSONB,
    output_state JSONB,
    next_action TEXT,
    execution_time DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Memory and RAG System
CREATE TABLE dev.memories (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    importance_score DOUBLE PRECISION DEFAULT 0.5,
    user_id INTEGER REFERENCES dev.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE dev.rag_documents (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    embedding VECTOR(1536),
    chunk_index INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- 6. Models and AI
CREATE TABLE dev.models (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_type TEXT NOT NULL,
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE dev.model_embedding (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES dev.models(id) ON DELETE CASCADE,
    input_text TEXT NOT NULL,
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE dev.model_capabilities (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES dev.models(id) ON DELETE CASCADE,
    capability TEXT NOT NULL,
    performance_score DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. Business Logic Tables
CREATE TABLE dev.deployments (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    environment TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    deployed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    config JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE dev.subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dev.users(id) ON DELETE CASCADE,
    plan_name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- 8. Caching and Performance
CREATE TABLE dev.weather_cache (
    id SERIAL PRIMARY KEY,
    location TEXT NOT NULL,
    weather_data JSONB NOT NULL,
    cached_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE dev.recommendation_cache (
    id SERIAL PRIMARY KEY,
    cache_key TEXT UNIQUE NOT NULL,
    recommendations JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- 9. Analytics and Usage
CREATE TABLE dev.api_usage (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dev.users(id),
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER,
    response_time DOUBLE PRECISION,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE dev.selection_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dev.users(id),
    selection_type TEXT NOT NULL, -- tool, prompt, resource
    selection_name TEXT NOT NULL,
    context TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- 10. Database Metadata for Analytics
CREATE TABLE dev.db_metadata_embedding (
    id SERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    column_name TEXT,
    description TEXT,
    data_type TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 11. Security and Audit
CREATE TABLE dev.audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dev.users(id),
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    old_values JSONB,
    new_values JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address INET
);

CREATE TABLE dev.authorization_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dev.users(id),
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    reviewer_id INTEGER REFERENCES dev.users(id)
);

-- 12. E-commerce Integration
CREATE TABLE dev.shopping_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dev.users(id),
    event_type TEXT NOT NULL,
    product_data JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Create indexes for performance
CREATE INDEX idx_tool_embeddings_name ON dev.tool_embeddings(tool_name);
CREATE INDEX idx_tool_embeddings_category ON dev.tool_embeddings(category);
CREATE INDEX idx_tool_selections_timestamp ON dev.tool_selections(timestamp);
CREATE INDEX idx_spans_trace_id ON dev.spans(trace_id);
CREATE INDEX idx_span_logs_span_id ON dev.span_logs(span_id);
CREATE INDEX idx_langgraph_executions_trace_id ON dev.langgraph_executions(trace_id);
CREATE INDEX idx_memories_user_id ON dev.memories(user_id);
CREATE INDEX idx_selection_history_user_id ON dev.selection_history(user_id);
CREATE INDEX idx_selection_history_type ON dev.selection_history(selection_type);

-- Vector similarity search indexes (using cosine distance)
CREATE INDEX idx_tool_embeddings_vector ON dev.tool_embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_prompt_embeddings_vector ON dev.prompt_embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_resource_embeddings_vector ON dev.resource_embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_memories_vector ON dev.memories USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_rag_documents_vector ON dev.rag_documents USING ivfflat (embedding vector_cosine_ops);

-- Add comments for documentation
COMMENT ON TABLE dev.tool_embeddings IS 'Vector embeddings for semantic tool search and selection';
COMMENT ON TABLE dev.tool_selections IS 'History of tool selections with similarity scores';
COMMENT ON TABLE dev.spans IS 'Distributed tracing spans for operation monitoring';
COMMENT ON TABLE dev.span_logs IS 'Detailed logs for tracing spans';
COMMENT ON TABLE dev.langgraph_executions IS 'LangGraph node execution records';

-- Reset search_path
RESET search_path;