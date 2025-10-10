create schema if not exists "dev";

create sequence "dev"."carts_id_seq";

create sequence "dev"."events_id_seq";

create sequence "dev"."langgraph_executions_id_seq";

create sequence "dev"."mcp_prompts_id_seq";

create sequence "dev"."mcp_resources_id_seq";

create sequence "dev"."mcp_search_history_id_seq";

create sequence "dev"."mcp_tools_id_seq";

create sequence "dev"."mcp_unified_search_embeddings_id_seq";

create sequence "dev"."model_embeddings_id_seq";

create sequence "dev"."model_statistics_id_seq";

create sequence "dev"."orders_id_seq";

create sequence "dev"."prompt_embeddings_id_seq";

create sequence "dev"."resource_embeddings_id_seq";

create sequence "dev"."sessions_id_seq";

create sequence "dev"."span_logs_id_seq";

create sequence "dev"."subscriptions_id_seq";

create sequence "dev"."tool_embeddings_id_seq";

create sequence "dev"."user_credit_transactions_id_seq";

create sequence "dev"."user_tasks_id_seq";

create sequence "dev"."user_usage_records_id_seq";

create sequence "dev"."users_id_seq";

create table "dev"."carts" (
    "id" integer not null default nextval('dev.carts_id_seq'::regclass),
    "cart_id" character varying(255) not null,
    "user_id" character varying(255),
    "cart_data" jsonb default '{}'::jsonb,
    "total_amount" numeric(10,2) default 0.00,
    "currency" character varying(3) default 'USD'::character varying,
    "status" character varying(50) default 'active'::character varying,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now(),
    "expires_at" timestamp with time zone
);


create table "dev"."checkpoint_blobs" (
    "thread_id" text not null,
    "checkpoint_ns" text not null default ''::text,
    "channel" text not null,
    "version" text not null,
    "type" text not null,
    "blob" bytea
);


create table "dev"."checkpoint_migrations" (
    "v" integer not null
);


create table "dev"."checkpoint_writes" (
    "thread_id" text not null,
    "checkpoint_ns" text not null default ''::text,
    "checkpoint_id" text not null,
    "task_id" text not null,
    "idx" integer not null,
    "channel" text not null,
    "type" text,
    "blob" bytea not null,
    "task_path" text not null default ''::text
);


create table "dev"."checkpoints" (
    "thread_id" text not null,
    "checkpoint_ns" text not null default ''::text,
    "checkpoint_id" text not null,
    "parent_checkpoint_id" text,
    "type" text,
    "checkpoint" jsonb not null,
    "metadata" jsonb not null default '{}'::jsonb
);


create table "dev"."db_meta_embedding" (
    "id" text not null,
    "entity_type" text not null,
    "entity_name" text not null,
    "entity_full_name" text not null,
    "content" text not null,
    "embedding" vector(1536),
    "metadata" jsonb default '{}'::jsonb,
    "semantic_tags" text[] default '{}'::text[],
    "confidence_score" double precision default 0.0,
    "source_step" integer default 2,
    "database_source" text default ''::text,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."episodic_memories" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" character varying(255),
    "episode_title" character varying(300) not null,
    "summary" text not null,
    "participants" jsonb default '[]'::jsonb,
    "location" character varying(200),
    "temporal_context" character varying(100),
    "key_events" jsonb not null,
    "emotional_context" character varying(50),
    "outcomes" jsonb default '[]'::jsonb,
    "lessons_learned" text,
    "embedding" vector(1536),
    "emotional_intensity" double precision default 0.5,
    "recall_frequency" integer default 0,
    "last_recalled_at" timestamp with time zone,
    "occurred_at" timestamp with time zone not null,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."events" (
    "id" integer not null default nextval('dev.events_id_seq'::regclass),
    "event_id" uuid default uuid_generate_v4(),
    "task_id" uuid,
    "user_id" character varying(255),
    "event_type" character varying(100) not null,
    "event_data" jsonb,
    "source" character varying(100) default 'event_sourcing_service'::character varying,
    "priority" integer default 1,
    "processed" boolean default false,
    "processed_at" timestamp with time zone,
    "agent_response" jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."factual_memories" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" character varying(255),
    "fact_type" character varying(50) not null,
    "subject" character varying(200) not null,
    "predicate" character varying(200) not null,
    "object_value" text not null,
    "context" text,
    "confidence" double precision default 0.8,
    "source_interaction_id" uuid,
    "embedding" vector(1536),
    "importance_score" double precision default 0.5,
    "last_confirmed_at" timestamp with time zone default now(),
    "expires_at" timestamp with time zone,
    "is_active" boolean default true,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."langgraph_executions" (
    "id" integer not null default nextval('dev.langgraph_executions_id_seq'::regclass),
    "trace_id" character varying(255),
    "span_id" character varying(255),
    "user_id" character varying(255),
    "node_name" character varying(255),
    "execution_order" integer,
    "input_state" jsonb,
    "output_state" jsonb,
    "next_action" character varying(255),
    "execution_time" double precision,
    "created_at" timestamp with time zone default now()
);


create table "dev"."mcp_prompts" (
    "id" integer not null default nextval('dev.mcp_prompts_id_seq'::regclass),
    "name" character varying(255) not null,
    "description" text,
    "category" character varying(100),
    "arguments" jsonb default '[]'::jsonb,
    "content" text,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now(),
    "last_modified" timestamp with time zone default now(),
    "usage_count" integer default 0,
    "is_active" boolean default true
);


create table "dev"."mcp_resources" (
    "id" integer not null default nextval('dev.mcp_resources_id_seq'::regclass),
    "uri" character varying(500) not null,
    "name" character varying(255) not null,
    "description" text,
    "resource_type" character varying(100),
    "mime_type" character varying(100),
    "size_bytes" bigint default 0,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now(),
    "last_accessed" timestamp with time zone,
    "access_count" integer default 0,
    "is_active" boolean default true
);


create table "dev"."mcp_search_history" (
    "id" integer not null default nextval('dev.mcp_search_history_id_seq'::regclass),
    "query" text not null,
    "filters" jsonb,
    "results_count" integer,
    "top_results" text[],
    "result_types" text[],
    "user_id" text,
    "session_id" text,
    "response_time_ms" integer,
    "created_at" timestamp with time zone default now()
);


create table "dev"."mcp_tools" (
    "id" integer not null default nextval('dev.mcp_tools_id_seq'::regclass),
    "name" character varying(255) not null,
    "description" text,
    "category" character varying(100),
    "input_schema" jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now(),
    "last_used" timestamp with time zone,
    "call_count" integer default 0,
    "avg_response_time" integer default 0,
    "success_rate" numeric(5,2) default 100.0,
    "is_active" boolean default true
);


create table "dev"."mcp_unified_search_embeddings" (
    "id" integer not null default nextval('dev.mcp_unified_search_embeddings_id_seq'::regclass),
    "item_name" text not null,
    "item_type" text not null,
    "category" text not null,
    "description" text,
    "embedding" vector(1536),
    "keywords" text[],
    "metadata" jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."memory_associations" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" character varying(255),
    "source_memory_type" character varying(20) not null,
    "source_memory_id" uuid not null,
    "target_memory_type" character varying(20) not null,
    "target_memory_id" uuid not null,
    "association_type" character varying(50) not null,
    "strength" double precision default 0.5,
    "context" text,
    "auto_discovered" boolean default false,
    "confirmation_count" integer default 0,
    "created_at" timestamp with time zone default now()
);


create table "dev"."memory_config" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" character varying(255),
    "max_factual_memories" integer default 10000,
    "max_procedural_memories" integer default 1000,
    "default_similarity_threshold" double precision default 0.7,
    "enable_auto_learning" boolean default true,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."memory_extraction_logs" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" character varying(255),
    "extraction_session_id" uuid not null,
    "source_content_hash" character varying(64),
    "extracted_memories" jsonb not null,
    "extraction_method" character varying(50) not null,
    "confidence_score" double precision,
    "created_at" timestamp with time zone default now()
);


create table "dev"."memory_metadata" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" character varying(255),
    "memory_type" character varying(20) not null,
    "memory_id" uuid not null,
    "access_count" integer default 0,
    "last_accessed_at" timestamp with time zone,
    "first_accessed_at" timestamp with time zone default now(),
    "modification_count" integer default 0,
    "last_modified_at" timestamp with time zone,
    "version" integer default 1,
    "accuracy_score" double precision,
    "relevance_score" double precision,
    "completeness_score" double precision,
    "user_rating" integer,
    "user_feedback" text,
    "feedback_timestamp" timestamp with time zone,
    "system_flags" jsonb default '{}'::jsonb,
    "priority_level" integer default 3,
    "dependency_count" integer default 0,
    "reference_count" integer default 0,
    "lifecycle_stage" character varying(20) default 'active'::character varying,
    "auto_expire" boolean default false,
    "expire_after_days" integer,
    "reinforcement_score" double precision default 0.0,
    "learning_curve" jsonb default '[]'::jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."memory_statistics" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" character varying(255),
    "period_type" character varying(20) not null,
    "period_start" timestamp with time zone not null,
    "period_end" timestamp with time zone not null,
    "factual_count" integer default 0,
    "procedural_count" integer default 0,
    "episodic_count" integer default 0,
    "semantic_count" integer default 0,
    "working_count" integer default 0,
    "total_accesses" integer default 0,
    "created_at" timestamp with time zone default now()
);


create table "dev"."model_capabilities" (
    "model_id" text not null,
    "capability" text not null,
    "created_at" timestamp with time zone default now()
);


create table "dev"."model_embeddings" (
    "id" bigint not null default nextval('dev.model_embeddings_id_seq'::regclass),
    "model_id" text,
    "provider" text not null,
    "description" text not null,
    "embedding" jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."model_statistics" (
    "id" bigint not null default nextval('dev.model_statistics_id_seq'::regclass),
    "model_id" text not null,
    "provider" text not null,
    "service_type" text not null,
    "operation_type" text not null,
    "date" date not null default CURRENT_DATE,
    "total_requests" integer default 0,
    "total_input_tokens" bigint default 0,
    "total_output_tokens" bigint default 0,
    "total_tokens" bigint default 0,
    "total_input_units" numeric default 0,
    "total_output_units" numeric default 0,
    "total_cost_usd" numeric(12,8) default 0,
    "last_updated" timestamp with time zone default now(),
    "created_at" timestamp with time zone default now()
);


create table "dev"."models" (
    "model_id" text not null,
    "model_type" text not null,
    "provider" text not null,
    "metadata" jsonb default '{}'::jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."orders" (
    "id" integer not null default nextval('dev.orders_id_seq'::regclass),
    "order_id" character varying(255) not null,
    "user_id" character varying(255),
    "shopify_order_id" character varying(255),
    "order_data" jsonb default '{}'::jsonb,
    "total_amount" numeric(10,2) not null,
    "currency" character varying(3) default 'USD'::character varying,
    "status" character varying(50) default 'pending'::character varying,
    "payment_status" character varying(50) default 'unpaid'::character varying,
    "fulfillment_status" character varying(50) default 'unfulfilled'::character varying,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."procedural_memories" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" character varying(255),
    "procedure_name" character varying(200) not null,
    "domain" character varying(100) not null,
    "trigger_conditions" jsonb not null,
    "steps" jsonb not null,
    "expected_outcome" text,
    "success_rate" double precision default 0.0,
    "usage_count" integer default 0,
    "last_used_at" timestamp with time zone,
    "embedding" vector(1536),
    "difficulty_level" integer,
    "estimated_time_minutes" integer,
    "required_tools" jsonb default '[]'::jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."prompt_embeddings" (
    "id" bigint not null default nextval('dev.prompt_embeddings_id_seq'::regclass),
    "prompt_name" text not null,
    "description" text,
    "embedding" jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."resource_embeddings" (
    "id" bigint not null default nextval('dev.resource_embeddings_id_seq'::regclass),
    "resource_uri" text not null,
    "category" text,
    "name" text,
    "description" text,
    "embedding" jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."semantic_memories" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" character varying(255),
    "concept_name" character varying(200) not null,
    "concept_category" character varying(100) not null,
    "definition" text not null,
    "properties" jsonb default '{}'::jsonb,
    "related_concepts" jsonb default '[]'::jsonb,
    "hierarchical_level" integer default 0,
    "parent_concept_id" uuid,
    "use_cases" jsonb default '[]'::jsonb,
    "examples" jsonb default '[]'::jsonb,
    "embedding" vector(1536),
    "mastery_level" double precision default 0.5,
    "learning_source" character varying(100),
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."session_memories" (
    "id" uuid not null default gen_random_uuid(),
    "session_id" character varying(64) not null,
    "user_id" uuid,
    "conversation_summary" text,
    "user_context" jsonb default '{}'::jsonb,
    "key_decisions" jsonb default '[]'::jsonb,
    "ongoing_tasks" jsonb default '[]'::jsonb,
    "user_preferences" jsonb default '{}'::jsonb,
    "important_facts" jsonb default '[]'::jsonb,
    "total_messages" integer default 0,
    "messages_since_last_summary" integer default 0,
    "last_summary_at" timestamp with time zone,
    "is_active" boolean default true,
    "session_metadata" jsonb default '{}'::jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."session_messages" (
    "id" uuid not null default gen_random_uuid(),
    "session_id" character varying(64) not null,
    "user_id" uuid,
    "message_type" character varying(20) not null,
    "role" character varying(20) not null,
    "content" text not null,
    "tool_calls" jsonb,
    "tool_call_id" character varying(100),
    "message_metadata" jsonb default '{}'::jsonb,
    "tokens_used" integer default 0,
    "cost_usd" numeric(10,8) default 0,
    "is_summary_candidate" boolean default true,
    "importance_score" double precision default 0.5,
    "created_at" timestamp with time zone default now()
);


create table "dev"."sessions" (
    "id" integer not null default nextval('dev.sessions_id_seq'::regclass),
    "session_id" character varying(255) not null,
    "user_id" character varying(255),
    "conversation_data" jsonb default '{}'::jsonb,
    "status" character varying(50) default 'active'::character varying,
    "created_at" timestamp with time zone default now(),
    "expires_at" timestamp with time zone,
    "updated_at" timestamp with time zone default now(),
    "last_activity" timestamp with time zone default now(),
    "is_active" boolean default true,
    "message_count" integer default 0,
    "total_tokens" integer default 0,
    "total_cost" numeric(10,6) default 0.0,
    "metadata" jsonb default '{}'::jsonb,
    "session_summary" text default ''::text
);


create table "dev"."span_logs" (
    "id" integer not null default nextval('dev.span_logs_id_seq'::regclass),
    "span_id" character varying(255),
    "timestamp" timestamp with time zone default now(),
    "level" character varying(20),
    "message" text,
    "fields" jsonb default '{}'::jsonb
);


create table "dev"."spans" (
    "span_id" character varying(255) not null,
    "trace_id" character varying(255),
    "parent_span_id" character varying(255),
    "operation_name" character varying(255),
    "start_time" timestamp with time zone default now(),
    "end_time" timestamp with time zone,
    "duration" double precision,
    "tags" jsonb default '{}'::jsonb,
    "created_at" timestamp with time zone default now(),
    "status" text default 'running'::text,
    "error_message" text
);


create table "dev"."subscriptions" (
    "id" integer not null default nextval('dev.subscriptions_id_seq'::regclass),
    "user_id" character varying(255),
    "subscription_scope" character varying(50) not null,
    "app_id" character varying(255),
    "stripe_subscription_id" character varying(255),
    "stripe_customer_id" character varying(255),
    "status" character varying(50) default 'inactive'::character varying,
    "plan_type" character varying(50) default 'free'::character varying,
    "credits_included" integer default 0,
    "current_period_start" timestamp with time zone,
    "current_period_end" timestamp with time zone,
    "canceled_at" timestamp with time zone,
    "downgrade_at_period_end" boolean default false,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."tool_embeddings" (
    "id" bigint not null default nextval('dev.tool_embeddings_id_seq'::regclass),
    "tool_name" text not null,
    "description" text,
    "embedding" jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."traces" (
    "trace_id" character varying(255) not null,
    "user_id" character varying(255),
    "session_id" character varying(255),
    "operation_name" character varying(255),
    "start_time" timestamp with time zone default now(),
    "end_time" timestamp with time zone,
    "duration" double precision,
    "status" character varying(50),
    "tags" jsonb default '{}'::jsonb,
    "created_at" timestamp with time zone default now(),
    "service_name" text not null default 'agent-service'::text,
    "total_spans" integer default 0,
    "error_message" text
);


create table "dev"."user_credit_transactions" (
    "id" bigint not null default nextval('dev.user_credit_transactions_id_seq'::regclass),
    "user_id" character varying not null,
    "transaction_type" character varying not null,
    "credits_amount" numeric(10,3) not null,
    "credits_before" numeric(10,3) not null,
    "credits_after" numeric(10,3) not null,
    "usage_record_id" bigint,
    "description" text,
    "metadata" jsonb default '{}'::jsonb,
    "created_at" timestamp with time zone default now()
);


create table "dev"."user_knowledge" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" text not null,
    "text" text not null,
    "embedding_vector" vector(1536),
    "metadata" jsonb default '{}'::jsonb,
    "chunk_index" integer default 0,
    "source_document" text,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."user_tasks" (
    "id" integer not null default nextval('dev.user_tasks_id_seq'::regclass),
    "task_id" uuid default uuid_generate_v4(),
    "user_id" character varying(255),
    "task_type" character varying(100) not null,
    "description" text,
    "config" jsonb,
    "callback_url" character varying(500),
    "status" character varying(50) default 'active'::character varying,
    "last_check" timestamp with time zone,
    "next_check" timestamp with time zone,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."user_usage_records" (
    "id" bigint not null default nextval('dev.user_usage_records_id_seq'::regclass),
    "user_id" character varying not null,
    "session_id" character varying,
    "trace_id" character varying,
    "endpoint" character varying not null,
    "event_type" character varying not null,
    "credits_charged" numeric(10,3) not null default 0,
    "cost_usd" numeric(10,6) not null default 0,
    "calculation_method" character varying default 'unknown'::character varying,
    "tokens_used" integer default 0,
    "prompt_tokens" integer default 0,
    "completion_tokens" integer default 0,
    "model_name" character varying,
    "provider" character varying,
    "tool_name" character varying,
    "operation_name" character varying,
    "billing_metadata" jsonb default '{}'::jsonb,
    "request_data" jsonb default '{}'::jsonb,
    "response_data" jsonb default '{}'::jsonb,
    "created_at" timestamp with time zone default now()
);


create table "dev"."users" (
    "id" integer not null default nextval('dev.users_id_seq'::regclass),
    "user_id" character varying(255) not null,
    "auth0_id" character varying(255),
    "email" character varying(255),
    "phone" character varying(50),
    "name" character varying(255),
    "credits_remaining" numeric(10,3) default 1000,
    "credits_total" numeric(10,3) default 1000,
    "subscription_status" character varying(50) default 'free'::character varying,
    "is_active" boolean default true,
    "shipping_addresses" jsonb default '[]'::jsonb,
    "payment_methods" jsonb default '[]'::jsonb,
    "preferences" jsonb default '{}'::jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


create table "dev"."working_memories" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" character varying(255),
    "context_type" character varying(50) not null,
    "context_id" character varying(200) not null,
    "state_data" jsonb not null,
    "current_step" character varying(200),
    "progress_percentage" double precision default 0.0,
    "next_actions" jsonb default '[]'::jsonb,
    "dependencies" jsonb default '[]'::jsonb,
    "blocking_issues" jsonb default '[]'::jsonb,
    "embedding" vector(1536),
    "priority" integer default 3,
    "expires_at" timestamp with time zone default (now() + '24:00:00'::interval),
    "is_active" boolean default true,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
);


alter sequence "dev"."carts_id_seq" owned by "dev"."carts"."id";

alter sequence "dev"."events_id_seq" owned by "dev"."events"."id";

alter sequence "dev"."langgraph_executions_id_seq" owned by "dev"."langgraph_executions"."id";

alter sequence "dev"."mcp_prompts_id_seq" owned by "dev"."mcp_prompts"."id";

alter sequence "dev"."mcp_resources_id_seq" owned by "dev"."mcp_resources"."id";

alter sequence "dev"."mcp_search_history_id_seq" owned by "dev"."mcp_search_history"."id";

alter sequence "dev"."mcp_tools_id_seq" owned by "dev"."mcp_tools"."id";

alter sequence "dev"."mcp_unified_search_embeddings_id_seq" owned by "dev"."mcp_unified_search_embeddings"."id";

alter sequence "dev"."model_embeddings_id_seq" owned by "dev"."model_embeddings"."id";

alter sequence "dev"."model_statistics_id_seq" owned by "dev"."model_statistics"."id";

alter sequence "dev"."orders_id_seq" owned by "dev"."orders"."id";

alter sequence "dev"."prompt_embeddings_id_seq" owned by "dev"."prompt_embeddings"."id";

alter sequence "dev"."resource_embeddings_id_seq" owned by "dev"."resource_embeddings"."id";

alter sequence "dev"."sessions_id_seq" owned by "dev"."sessions"."id";

alter sequence "dev"."span_logs_id_seq" owned by "dev"."span_logs"."id";

alter sequence "dev"."subscriptions_id_seq" owned by "dev"."subscriptions"."id";

alter sequence "dev"."tool_embeddings_id_seq" owned by "dev"."tool_embeddings"."id";

alter sequence "dev"."user_credit_transactions_id_seq" owned by "dev"."user_credit_transactions"."id";

alter sequence "dev"."user_tasks_id_seq" owned by "dev"."user_tasks"."id";

alter sequence "dev"."user_usage_records_id_seq" owned by "dev"."user_usage_records"."id";

alter sequence "dev"."users_id_seq" owned by "dev"."users"."id";

CREATE UNIQUE INDEX carts_cart_id_key ON dev.carts USING btree (cart_id);

CREATE UNIQUE INDEX carts_pkey ON dev.carts USING btree (id);

CREATE UNIQUE INDEX checkpoint_blobs_pkey ON dev.checkpoint_blobs USING btree (thread_id, checkpoint_ns, channel, version);

CREATE INDEX checkpoint_blobs_thread_id_idx ON dev.checkpoint_blobs USING btree (thread_id);

CREATE UNIQUE INDEX checkpoint_migrations_pkey ON dev.checkpoint_migrations USING btree (v);

CREATE UNIQUE INDEX checkpoint_writes_pkey ON dev.checkpoint_writes USING btree (thread_id, checkpoint_ns, checkpoint_id, task_id, idx);

CREATE INDEX checkpoint_writes_thread_id_idx ON dev.checkpoint_writes USING btree (thread_id);

CREATE UNIQUE INDEX checkpoints_pkey ON dev.checkpoints USING btree (thread_id, checkpoint_ns, checkpoint_id);

CREATE INDEX checkpoints_thread_id_idx ON dev.checkpoints USING btree (thread_id);

CREATE INDEX db_meta_embedding_confidence_idx ON dev.db_meta_embedding USING btree (confidence_score);

CREATE INDEX db_meta_embedding_created_at_idx ON dev.db_meta_embedding USING btree (created_at);

CREATE INDEX db_meta_embedding_entity_name_idx ON dev.db_meta_embedding USING btree (entity_name);

CREATE INDEX db_meta_embedding_entity_type_idx ON dev.db_meta_embedding USING btree (entity_type);

CREATE UNIQUE INDEX db_meta_embedding_pkey ON dev.db_meta_embedding USING btree (id);

CREATE INDEX db_meta_embedding_source_idx ON dev.db_meta_embedding USING btree (database_source);

CREATE INDEX db_meta_embedding_vector_idx ON dev.db_meta_embedding USING ivfflat (embedding vector_cosine_ops) WITH (lists='100');

CREATE UNIQUE INDEX episodic_memories_pkey ON dev.episodic_memories USING btree (id);

CREATE UNIQUE INDEX events_pkey ON dev.events USING btree (id);

CREATE UNIQUE INDEX factual_memories_pkey ON dev.factual_memories USING btree (id);

CREATE UNIQUE INDEX factual_memories_user_id_fact_type_subject_predicate_key ON dev.factual_memories USING btree (user_id, fact_type, subject, predicate);

CREATE INDEX idx_associations_source ON dev.memory_associations USING btree (source_memory_type, source_memory_id);

CREATE INDEX idx_associations_strength ON dev.memory_associations USING btree (strength DESC);

CREATE INDEX idx_associations_target ON dev.memory_associations USING btree (target_memory_type, target_memory_id);

CREATE INDEX idx_associations_user ON dev.memory_associations USING btree (user_id);

CREATE INDEX idx_carts_expires_at ON dev.carts USING btree (expires_at);

CREATE INDEX idx_carts_status ON dev.carts USING btree (status);

CREATE INDEX idx_carts_user_id ON dev.carts USING btree (user_id);

CREATE INDEX idx_credit_transactions_created_at ON dev.user_credit_transactions USING btree (created_at);

CREATE INDEX idx_credit_transactions_user_id ON dev.user_credit_transactions USING btree (user_id);

CREATE INDEX idx_dev_capabilities_capability ON dev.model_capabilities USING btree (capability);

CREATE INDEX idx_dev_embeddings_model_id ON dev.model_embeddings USING btree (model_id);

CREATE INDEX idx_dev_model_stats_date ON dev.model_statistics USING btree (date);

CREATE INDEX idx_dev_model_stats_model_id ON dev.model_statistics USING btree (model_id);

CREATE INDEX idx_dev_model_stats_operation_type ON dev.model_statistics USING btree (operation_type);

CREATE INDEX idx_dev_model_stats_provider ON dev.model_statistics USING btree (provider);

CREATE INDEX idx_dev_model_stats_service_type ON dev.model_statistics USING btree (service_type);

CREATE INDEX idx_dev_models_provider ON dev.models USING btree (provider);

CREATE INDEX idx_dev_models_type ON dev.models USING btree (model_type);

CREATE INDEX idx_dev_prompt_embeddings_name ON dev.prompt_embeddings USING btree (prompt_name);

CREATE INDEX idx_dev_resource_embeddings_category ON dev.resource_embeddings USING btree (category);

CREATE INDEX idx_dev_resource_embeddings_uri ON dev.resource_embeddings USING btree (resource_uri);

CREATE INDEX idx_dev_tool_embeddings_name ON dev.tool_embeddings USING btree (tool_name);

CREATE INDEX idx_episodic_embedding ON dev.episodic_memories USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX idx_episodic_emotional ON dev.episodic_memories USING btree (emotional_intensity DESC);

CREATE INDEX idx_episodic_location ON dev.episodic_memories USING btree (user_id, location) WHERE (location IS NOT NULL);

CREATE INDEX idx_episodic_user_time ON dev.episodic_memories USING btree (user_id, occurred_at DESC);

CREATE INDEX idx_events_created_at ON dev.events USING btree (created_at);

CREATE INDEX idx_events_event_id ON dev.events USING btree (event_id);

CREATE INDEX idx_events_processed ON dev.events USING btree (processed);

CREATE INDEX idx_events_task_id ON dev.events USING btree (task_id);

CREATE INDEX idx_events_type ON dev.events USING btree (event_type);

CREATE INDEX idx_events_user_id ON dev.events USING btree (user_id);

CREATE INDEX idx_factual_embedding ON dev.factual_memories USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX idx_factual_importance ON dev.factual_memories USING btree (importance_score DESC);

CREATE INDEX idx_factual_subject ON dev.factual_memories USING btree (user_id, subject);

CREATE INDEX idx_factual_user_type ON dev.factual_memories USING btree (user_id, fact_type);

CREATE INDEX idx_langgraph_node_name ON dev.langgraph_executions USING btree (node_name);

CREATE INDEX idx_langgraph_span_id ON dev.langgraph_executions USING btree (span_id);

CREATE INDEX idx_langgraph_trace_id ON dev.langgraph_executions USING btree (trace_id);

CREATE INDEX idx_langgraph_user_id ON dev.langgraph_executions USING btree (user_id);

CREATE INDEX idx_mcp_prompts_active ON dev.mcp_prompts USING btree (is_active);

CREATE INDEX idx_mcp_prompts_category ON dev.mcp_prompts USING btree (category);

CREATE INDEX idx_mcp_resources_active ON dev.mcp_resources USING btree (is_active);

CREATE INDEX idx_mcp_resources_type ON dev.mcp_resources USING btree (resource_type);

CREATE INDEX idx_mcp_search_history_created ON dev.mcp_search_history USING btree (created_at);

CREATE INDEX idx_mcp_search_history_query ON dev.mcp_search_history USING btree (query);

CREATE INDEX idx_mcp_search_history_user ON dev.mcp_search_history USING btree (user_id);

CREATE INDEX idx_mcp_tools_active ON dev.mcp_tools USING btree (is_active);

CREATE INDEX idx_mcp_tools_category ON dev.mcp_tools USING btree (category);

CREATE INDEX idx_mcp_unified_search_embeddings_category ON dev.mcp_unified_search_embeddings USING btree (category);

CREATE INDEX idx_mcp_unified_search_embeddings_name ON dev.mcp_unified_search_embeddings USING btree (item_name);

CREATE INDEX idx_mcp_unified_search_embeddings_type ON dev.mcp_unified_search_embeddings USING btree (item_type);

CREATE INDEX idx_mcp_unified_search_embeddings_updated ON dev.mcp_unified_search_embeddings USING btree (updated_at);

CREATE INDEX idx_mcp_unified_search_embeddings_vector ON dev.mcp_unified_search_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists='100');

CREATE INDEX idx_metadata_access ON dev.memory_metadata USING btree (access_count DESC);

CREATE INDEX idx_metadata_flags ON dev.memory_metadata USING gin (system_flags);

CREATE INDEX idx_metadata_lifecycle ON dev.memory_metadata USING btree (lifecycle_stage);

CREATE INDEX idx_metadata_memory ON dev.memory_metadata USING btree (memory_type, memory_id);

CREATE INDEX idx_metadata_priority ON dev.memory_metadata USING btree (priority_level DESC);

CREATE INDEX idx_metadata_quality ON dev.memory_metadata USING btree (accuracy_score DESC, relevance_score DESC);

CREATE INDEX idx_metadata_user_type ON dev.memory_metadata USING btree (user_id, memory_type);

CREATE INDEX idx_orders_created_at ON dev.orders USING btree (created_at);

CREATE INDEX idx_orders_payment_status ON dev.orders USING btree (payment_status);

CREATE INDEX idx_orders_shopify_order_id ON dev.orders USING btree (shopify_order_id);

CREATE INDEX idx_orders_status ON dev.orders USING btree (status);

CREATE INDEX idx_orders_user_id ON dev.orders USING btree (user_id);

CREATE INDEX idx_procedural_embedding ON dev.procedural_memories USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX idx_procedural_usage ON dev.procedural_memories USING btree (usage_count DESC);

CREATE INDEX idx_procedural_user_domain ON dev.procedural_memories USING btree (user_id, domain);

CREATE INDEX idx_semantic_embedding ON dev.semantic_memories USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX idx_semantic_hierarchy ON dev.semantic_memories USING btree (parent_concept_id) WHERE (parent_concept_id IS NOT NULL);

CREATE INDEX idx_semantic_mastery ON dev.semantic_memories USING btree (mastery_level DESC);

CREATE INDEX idx_semantic_user_category ON dev.semantic_memories USING btree (user_id, concept_category);

CREATE INDEX idx_session_memories_active ON dev.session_memories USING btree (is_active, updated_at) WHERE (is_active = true);

CREATE INDEX idx_session_memories_user ON dev.session_memories USING btree (user_id);

CREATE INDEX idx_session_messages_session ON dev.session_messages USING btree (session_id);

CREATE INDEX idx_session_messages_time ON dev.session_messages USING btree (created_at DESC);

CREATE INDEX idx_session_messages_type ON dev.session_messages USING btree (message_type);

CREATE INDEX idx_sessions_expires_at ON dev.sessions USING btree (expires_at);

CREATE INDEX idx_sessions_is_active ON dev.sessions USING btree (is_active);

CREATE INDEX idx_sessions_last_activity ON dev.sessions USING btree (last_activity);

CREATE INDEX idx_sessions_message_count ON dev.sessions USING btree (message_count);

CREATE INDEX idx_sessions_session_id ON dev.sessions USING btree (session_id);

CREATE INDEX idx_sessions_status ON dev.sessions USING btree (status);

CREATE INDEX idx_sessions_user_id ON dev.sessions USING btree (user_id);

CREATE INDEX idx_span_logs_level ON dev.span_logs USING btree (level);

CREATE INDEX idx_span_logs_span_id ON dev.span_logs USING btree (span_id);

CREATE INDEX idx_span_logs_timestamp ON dev.span_logs USING btree ("timestamp");

CREATE INDEX idx_spans_operation_name ON dev.spans USING btree (operation_name);

CREATE INDEX idx_spans_parent_span_id ON dev.spans USING btree (parent_span_id);

CREATE INDEX idx_spans_start_time ON dev.spans USING btree (start_time);

CREATE INDEX idx_spans_trace_id ON dev.spans USING btree (trace_id);

CREATE INDEX idx_subscriptions_app_id ON dev.subscriptions USING btree (app_id);

CREATE INDEX idx_subscriptions_scope ON dev.subscriptions USING btree (subscription_scope);

CREATE INDEX idx_subscriptions_status ON dev.subscriptions USING btree (status);

CREATE INDEX idx_subscriptions_user_id ON dev.subscriptions USING btree (user_id);

CREATE INDEX idx_traces_session_id ON dev.traces USING btree (session_id);

CREATE INDEX idx_traces_start_time ON dev.traces USING btree (start_time);

CREATE INDEX idx_traces_status ON dev.traces USING btree (status);

CREATE INDEX idx_traces_user_id ON dev.traces USING btree (user_id);

CREATE INDEX idx_user_knowledge_created_at ON dev.user_knowledge USING btree (created_at);

CREATE INDEX idx_user_knowledge_metadata ON dev.user_knowledge USING gin (metadata);

CREATE INDEX idx_user_knowledge_user_id ON dev.user_knowledge USING btree (user_id);

CREATE INDEX idx_user_tasks_status ON dev.user_tasks USING btree (status);

CREATE INDEX idx_user_tasks_task_id ON dev.user_tasks USING btree (task_id);

CREATE INDEX idx_user_tasks_type ON dev.user_tasks USING btree (task_type);

CREATE INDEX idx_user_tasks_user_id ON dev.user_tasks USING btree (user_id);

CREATE INDEX idx_user_usage_records_created_at ON dev.user_usage_records USING btree (created_at);

CREATE INDEX idx_user_usage_records_event_type ON dev.user_usage_records USING btree (event_type);

CREATE INDEX idx_user_usage_records_session_id ON dev.user_usage_records USING btree (session_id);

CREATE INDEX idx_user_usage_records_user_id ON dev.user_usage_records USING btree (user_id);

CREATE INDEX idx_users_auth0_id ON dev.users USING btree (auth0_id);

CREATE INDEX idx_users_email ON dev.users USING btree (email);

CREATE INDEX idx_users_user_id ON dev.users USING btree (user_id);

CREATE INDEX idx_working_active ON dev.working_memories USING btree (user_id, is_active, expires_at) WHERE (is_active = true);

CREATE INDEX idx_working_embedding ON dev.working_memories USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX idx_working_priority ON dev.working_memories USING btree (priority DESC);

CREATE INDEX idx_working_user_type ON dev.working_memories USING btree (user_id, context_type);

CREATE UNIQUE INDEX langgraph_executions_pkey ON dev.langgraph_executions USING btree (id);

CREATE UNIQUE INDEX mcp_prompts_name_key ON dev.mcp_prompts USING btree (name);

CREATE UNIQUE INDEX mcp_prompts_pkey ON dev.mcp_prompts USING btree (id);

CREATE UNIQUE INDEX mcp_resources_pkey ON dev.mcp_resources USING btree (id);

CREATE UNIQUE INDEX mcp_resources_uri_key ON dev.mcp_resources USING btree (uri);

CREATE UNIQUE INDEX mcp_search_history_pkey ON dev.mcp_search_history USING btree (id);

CREATE UNIQUE INDEX mcp_tools_name_key ON dev.mcp_tools USING btree (name);

CREATE UNIQUE INDEX mcp_tools_pkey ON dev.mcp_tools USING btree (id);

CREATE UNIQUE INDEX mcp_unified_search_embeddings_item_name_key ON dev.mcp_unified_search_embeddings USING btree (item_name);

CREATE UNIQUE INDEX mcp_unified_search_embeddings_pkey ON dev.mcp_unified_search_embeddings USING btree (id);

CREATE UNIQUE INDEX memory_associations_pkey ON dev.memory_associations USING btree (id);

CREATE UNIQUE INDEX memory_associations_user_id_source_memory_type_source_memor_key ON dev.memory_associations USING btree (user_id, source_memory_type, source_memory_id, target_memory_type, target_memory_id, association_type);

CREATE UNIQUE INDEX memory_config_pkey ON dev.memory_config USING btree (id);

CREATE UNIQUE INDEX memory_config_user_id_key ON dev.memory_config USING btree (user_id);

CREATE UNIQUE INDEX memory_extraction_logs_pkey ON dev.memory_extraction_logs USING btree (id);

CREATE UNIQUE INDEX memory_metadata_pkey ON dev.memory_metadata USING btree (id);

CREATE UNIQUE INDEX memory_metadata_user_id_memory_type_memory_id_key ON dev.memory_metadata USING btree (user_id, memory_type, memory_id);

CREATE UNIQUE INDEX memory_statistics_pkey ON dev.memory_statistics USING btree (id);

CREATE UNIQUE INDEX memory_statistics_user_id_period_type_period_start_key ON dev.memory_statistics USING btree (user_id, period_type, period_start);

CREATE UNIQUE INDEX model_capabilities_pkey ON dev.model_capabilities USING btree (model_id, capability);

CREATE UNIQUE INDEX model_embeddings_pkey ON dev.model_embeddings USING btree (id);

CREATE UNIQUE INDEX model_statistics_pkey ON dev.model_statistics USING btree (id);

CREATE UNIQUE INDEX models_pkey ON dev.models USING btree (model_id);

CREATE UNIQUE INDEX orders_order_id_key ON dev.orders USING btree (order_id);

CREATE UNIQUE INDEX orders_pkey ON dev.orders USING btree (id);

CREATE UNIQUE INDEX procedural_memories_pkey ON dev.procedural_memories USING btree (id);

CREATE UNIQUE INDEX procedural_memories_user_id_procedure_name_domain_key ON dev.procedural_memories USING btree (user_id, procedure_name, domain);

CREATE UNIQUE INDEX prompt_embeddings_pkey ON dev.prompt_embeddings USING btree (id);

CREATE UNIQUE INDEX prompt_embeddings_prompt_name_key ON dev.prompt_embeddings USING btree (prompt_name);

CREATE UNIQUE INDEX resource_embeddings_pkey ON dev.resource_embeddings USING btree (id);

CREATE UNIQUE INDEX resource_embeddings_resource_uri_key ON dev.resource_embeddings USING btree (resource_uri);

CREATE UNIQUE INDEX semantic_memories_pkey ON dev.semantic_memories USING btree (id);

CREATE UNIQUE INDEX semantic_memories_user_id_concept_name_concept_category_key ON dev.semantic_memories USING btree (user_id, concept_name, concept_category);

CREATE UNIQUE INDEX session_memories_pkey ON dev.session_memories USING btree (id);

CREATE UNIQUE INDEX session_memories_session_id_key ON dev.session_memories USING btree (session_id);

CREATE UNIQUE INDEX session_messages_pkey ON dev.session_messages USING btree (id);

CREATE UNIQUE INDEX sessions_pkey ON dev.sessions USING btree (id);

CREATE UNIQUE INDEX sessions_session_id_key ON dev.sessions USING btree (session_id);

CREATE UNIQUE INDEX span_logs_pkey ON dev.span_logs USING btree (id);

CREATE UNIQUE INDEX spans_pkey ON dev.spans USING btree (span_id);

CREATE UNIQUE INDEX subscriptions_pkey ON dev.subscriptions USING btree (id);

CREATE UNIQUE INDEX tool_embeddings_pkey ON dev.tool_embeddings USING btree (id);

CREATE UNIQUE INDEX tool_embeddings_tool_name_key ON dev.tool_embeddings USING btree (tool_name);

CREATE UNIQUE INDEX traces_pkey ON dev.traces USING btree (trace_id);

CREATE UNIQUE INDEX unique_model_daily_stats ON dev.model_statistics USING btree (model_id, provider, service_type, operation_type, date);

CREATE UNIQUE INDEX user_credit_transactions_pkey ON dev.user_credit_transactions USING btree (id);

CREATE UNIQUE INDEX user_knowledge_pkey ON dev.user_knowledge USING btree (id);

CREATE UNIQUE INDEX user_tasks_pkey ON dev.user_tasks USING btree (id);

CREATE UNIQUE INDEX user_tasks_task_id_unique ON dev.user_tasks USING btree (task_id);

CREATE UNIQUE INDEX user_usage_records_pkey ON dev.user_usage_records USING btree (id);

CREATE UNIQUE INDEX users_auth0_id_key ON dev.users USING btree (auth0_id);

CREATE UNIQUE INDEX users_email_key ON dev.users USING btree (email);

CREATE UNIQUE INDEX users_pkey ON dev.users USING btree (id);

CREATE UNIQUE INDEX users_user_id_key ON dev.users USING btree (user_id);

CREATE UNIQUE INDEX working_memories_pkey ON dev.working_memories USING btree (id);

CREATE UNIQUE INDEX working_memories_user_id_context_type_context_id_key ON dev.working_memories USING btree (user_id, context_type, context_id);

alter table "dev"."carts" add constraint "carts_pkey" PRIMARY KEY using index "carts_pkey";

alter table "dev"."checkpoint_blobs" add constraint "checkpoint_blobs_pkey" PRIMARY KEY using index "checkpoint_blobs_pkey";

alter table "dev"."checkpoint_migrations" add constraint "checkpoint_migrations_pkey" PRIMARY KEY using index "checkpoint_migrations_pkey";

alter table "dev"."checkpoint_writes" add constraint "checkpoint_writes_pkey" PRIMARY KEY using index "checkpoint_writes_pkey";

alter table "dev"."checkpoints" add constraint "checkpoints_pkey" PRIMARY KEY using index "checkpoints_pkey";

alter table "dev"."db_meta_embedding" add constraint "db_meta_embedding_pkey" PRIMARY KEY using index "db_meta_embedding_pkey";

alter table "dev"."episodic_memories" add constraint "episodic_memories_pkey" PRIMARY KEY using index "episodic_memories_pkey";

alter table "dev"."events" add constraint "events_pkey" PRIMARY KEY using index "events_pkey";

alter table "dev"."factual_memories" add constraint "factual_memories_pkey" PRIMARY KEY using index "factual_memories_pkey";

alter table "dev"."langgraph_executions" add constraint "langgraph_executions_pkey" PRIMARY KEY using index "langgraph_executions_pkey";

alter table "dev"."mcp_prompts" add constraint "mcp_prompts_pkey" PRIMARY KEY using index "mcp_prompts_pkey";

alter table "dev"."mcp_resources" add constraint "mcp_resources_pkey" PRIMARY KEY using index "mcp_resources_pkey";

alter table "dev"."mcp_search_history" add constraint "mcp_search_history_pkey" PRIMARY KEY using index "mcp_search_history_pkey";

alter table "dev"."mcp_tools" add constraint "mcp_tools_pkey" PRIMARY KEY using index "mcp_tools_pkey";

alter table "dev"."mcp_unified_search_embeddings" add constraint "mcp_unified_search_embeddings_pkey" PRIMARY KEY using index "mcp_unified_search_embeddings_pkey";

alter table "dev"."memory_associations" add constraint "memory_associations_pkey" PRIMARY KEY using index "memory_associations_pkey";

alter table "dev"."memory_config" add constraint "memory_config_pkey" PRIMARY KEY using index "memory_config_pkey";

alter table "dev"."memory_extraction_logs" add constraint "memory_extraction_logs_pkey" PRIMARY KEY using index "memory_extraction_logs_pkey";

alter table "dev"."memory_metadata" add constraint "memory_metadata_pkey" PRIMARY KEY using index "memory_metadata_pkey";

alter table "dev"."memory_statistics" add constraint "memory_statistics_pkey" PRIMARY KEY using index "memory_statistics_pkey";

alter table "dev"."model_capabilities" add constraint "model_capabilities_pkey" PRIMARY KEY using index "model_capabilities_pkey";

alter table "dev"."model_embeddings" add constraint "model_embeddings_pkey" PRIMARY KEY using index "model_embeddings_pkey";

alter table "dev"."model_statistics" add constraint "model_statistics_pkey" PRIMARY KEY using index "model_statistics_pkey";

alter table "dev"."models" add constraint "models_pkey" PRIMARY KEY using index "models_pkey";

alter table "dev"."orders" add constraint "orders_pkey" PRIMARY KEY using index "orders_pkey";

alter table "dev"."procedural_memories" add constraint "procedural_memories_pkey" PRIMARY KEY using index "procedural_memories_pkey";

alter table "dev"."prompt_embeddings" add constraint "prompt_embeddings_pkey" PRIMARY KEY using index "prompt_embeddings_pkey";

alter table "dev"."resource_embeddings" add constraint "resource_embeddings_pkey" PRIMARY KEY using index "resource_embeddings_pkey";

alter table "dev"."semantic_memories" add constraint "semantic_memories_pkey" PRIMARY KEY using index "semantic_memories_pkey";

alter table "dev"."session_memories" add constraint "session_memories_pkey" PRIMARY KEY using index "session_memories_pkey";

alter table "dev"."session_messages" add constraint "session_messages_pkey" PRIMARY KEY using index "session_messages_pkey";

alter table "dev"."sessions" add constraint "sessions_pkey" PRIMARY KEY using index "sessions_pkey";

alter table "dev"."span_logs" add constraint "span_logs_pkey" PRIMARY KEY using index "span_logs_pkey";

alter table "dev"."spans" add constraint "spans_pkey" PRIMARY KEY using index "spans_pkey";

alter table "dev"."subscriptions" add constraint "subscriptions_pkey" PRIMARY KEY using index "subscriptions_pkey";

alter table "dev"."tool_embeddings" add constraint "tool_embeddings_pkey" PRIMARY KEY using index "tool_embeddings_pkey";

alter table "dev"."traces" add constraint "traces_pkey" PRIMARY KEY using index "traces_pkey";

alter table "dev"."user_credit_transactions" add constraint "user_credit_transactions_pkey" PRIMARY KEY using index "user_credit_transactions_pkey";

alter table "dev"."user_knowledge" add constraint "user_knowledge_pkey" PRIMARY KEY using index "user_knowledge_pkey";

alter table "dev"."user_tasks" add constraint "user_tasks_pkey" PRIMARY KEY using index "user_tasks_pkey";

alter table "dev"."user_usage_records" add constraint "user_usage_records_pkey" PRIMARY KEY using index "user_usage_records_pkey";

alter table "dev"."users" add constraint "users_pkey" PRIMARY KEY using index "users_pkey";

alter table "dev"."working_memories" add constraint "working_memories_pkey" PRIMARY KEY using index "working_memories_pkey";

alter table "dev"."carts" add constraint "carts_cart_id_key" UNIQUE using index "carts_cart_id_key";

alter table "dev"."carts" add constraint "carts_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) not valid;

alter table "dev"."carts" validate constraint "carts_user_id_fkey";

alter table "dev"."episodic_memories" add constraint "episodic_memories_emotional_intensity_check" CHECK (((emotional_intensity >= (0)::double precision) AND (emotional_intensity <= (1)::double precision))) not valid;

alter table "dev"."episodic_memories" validate constraint "episodic_memories_emotional_intensity_check";

alter table "dev"."episodic_memories" add constraint "episodic_memories_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."episodic_memories" validate constraint "episodic_memories_user_id_fkey";

alter table "dev"."events" add constraint "events_task_id_fkey" FOREIGN KEY (task_id) REFERENCES dev.user_tasks(task_id) not valid;

alter table "dev"."events" validate constraint "events_task_id_fkey";

alter table "dev"."events" add constraint "events_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) not valid;

alter table "dev"."events" validate constraint "events_user_id_fkey";

alter table "dev"."factual_memories" add constraint "factual_memories_confidence_check" CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision))) not valid;

alter table "dev"."factual_memories" validate constraint "factual_memories_confidence_check";

alter table "dev"."factual_memories" add constraint "factual_memories_user_id_fact_type_subject_predicate_key" UNIQUE using index "factual_memories_user_id_fact_type_subject_predicate_key";

alter table "dev"."factual_memories" add constraint "factual_memories_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."factual_memories" validate constraint "factual_memories_user_id_fkey";

alter table "dev"."langgraph_executions" add constraint "langgraph_executions_span_id_fkey" FOREIGN KEY (span_id) REFERENCES dev.spans(span_id) not valid;

alter table "dev"."langgraph_executions" validate constraint "langgraph_executions_span_id_fkey";

alter table "dev"."langgraph_executions" add constraint "langgraph_executions_trace_id_fkey" FOREIGN KEY (trace_id) REFERENCES dev.traces(trace_id) not valid;

alter table "dev"."langgraph_executions" validate constraint "langgraph_executions_trace_id_fkey";

alter table "dev"."langgraph_executions" add constraint "langgraph_executions_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) not valid;

alter table "dev"."langgraph_executions" validate constraint "langgraph_executions_user_id_fkey";

alter table "dev"."mcp_prompts" add constraint "mcp_prompts_name_key" UNIQUE using index "mcp_prompts_name_key";

alter table "dev"."mcp_resources" add constraint "mcp_resources_uri_key" UNIQUE using index "mcp_resources_uri_key";

alter table "dev"."mcp_tools" add constraint "mcp_tools_name_key" UNIQUE using index "mcp_tools_name_key";

alter table "dev"."mcp_unified_search_embeddings" add constraint "mcp_unified_search_embeddings_item_name_key" UNIQUE using index "mcp_unified_search_embeddings_item_name_key";

alter table "dev"."mcp_unified_search_embeddings" add constraint "mcp_unified_search_embeddings_item_type_check" CHECK ((item_type = ANY (ARRAY['tool'::text, 'prompt'::text, 'resource'::text]))) not valid;

alter table "dev"."mcp_unified_search_embeddings" validate constraint "mcp_unified_search_embeddings_item_type_check";

alter table "dev"."memory_associations" add constraint "memory_associations_source_memory_type_check" CHECK (((source_memory_type)::text = ANY ((ARRAY['factual'::character varying, 'procedural'::character varying, 'episodic'::character varying, 'semantic'::character varying, 'working'::character varying])::text[]))) not valid;

alter table "dev"."memory_associations" validate constraint "memory_associations_source_memory_type_check";

alter table "dev"."memory_associations" add constraint "memory_associations_strength_check" CHECK (((strength >= (0)::double precision) AND (strength <= (1)::double precision))) not valid;

alter table "dev"."memory_associations" validate constraint "memory_associations_strength_check";

alter table "dev"."memory_associations" add constraint "memory_associations_target_memory_type_check" CHECK (((target_memory_type)::text = ANY ((ARRAY['factual'::character varying, 'procedural'::character varying, 'episodic'::character varying, 'semantic'::character varying, 'working'::character varying])::text[]))) not valid;

alter table "dev"."memory_associations" validate constraint "memory_associations_target_memory_type_check";

alter table "dev"."memory_associations" add constraint "memory_associations_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."memory_associations" validate constraint "memory_associations_user_id_fkey";

alter table "dev"."memory_associations" add constraint "memory_associations_user_id_source_memory_type_source_memor_key" UNIQUE using index "memory_associations_user_id_source_memory_type_source_memor_key";

alter table "dev"."memory_config" add constraint "memory_config_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."memory_config" validate constraint "memory_config_user_id_fkey";

alter table "dev"."memory_config" add constraint "memory_config_user_id_key" UNIQUE using index "memory_config_user_id_key";

alter table "dev"."memory_extraction_logs" add constraint "memory_extraction_logs_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."memory_extraction_logs" validate constraint "memory_extraction_logs_user_id_fkey";

alter table "dev"."memory_metadata" add constraint "memory_metadata_accuracy_score_check" CHECK (((accuracy_score >= (0)::double precision) AND (accuracy_score <= (1)::double precision))) not valid;

alter table "dev"."memory_metadata" validate constraint "memory_metadata_accuracy_score_check";

alter table "dev"."memory_metadata" add constraint "memory_metadata_completeness_score_check" CHECK (((completeness_score >= (0)::double precision) AND (completeness_score <= (1)::double precision))) not valid;

alter table "dev"."memory_metadata" validate constraint "memory_metadata_completeness_score_check";

alter table "dev"."memory_metadata" add constraint "memory_metadata_lifecycle_stage_check" CHECK (((lifecycle_stage)::text = ANY ((ARRAY['active'::character varying, 'stale'::character varying, 'deprecated'::character varying, 'archived'::character varying])::text[]))) not valid;

alter table "dev"."memory_metadata" validate constraint "memory_metadata_lifecycle_stage_check";

alter table "dev"."memory_metadata" add constraint "memory_metadata_memory_type_check" CHECK (((memory_type)::text = ANY ((ARRAY['factual'::character varying, 'procedural'::character varying, 'episodic'::character varying, 'semantic'::character varying, 'working'::character varying])::text[]))) not valid;

alter table "dev"."memory_metadata" validate constraint "memory_metadata_memory_type_check";

alter table "dev"."memory_metadata" add constraint "memory_metadata_priority_level_check" CHECK (((priority_level >= 1) AND (priority_level <= 5))) not valid;

alter table "dev"."memory_metadata" validate constraint "memory_metadata_priority_level_check";

alter table "dev"."memory_metadata" add constraint "memory_metadata_relevance_score_check" CHECK (((relevance_score >= (0)::double precision) AND (relevance_score <= (1)::double precision))) not valid;

alter table "dev"."memory_metadata" validate constraint "memory_metadata_relevance_score_check";

alter table "dev"."memory_metadata" add constraint "memory_metadata_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."memory_metadata" validate constraint "memory_metadata_user_id_fkey";

alter table "dev"."memory_metadata" add constraint "memory_metadata_user_id_memory_type_memory_id_key" UNIQUE using index "memory_metadata_user_id_memory_type_memory_id_key";

alter table "dev"."memory_metadata" add constraint "memory_metadata_user_rating_check" CHECK (((user_rating >= 1) AND (user_rating <= 5))) not valid;

alter table "dev"."memory_metadata" validate constraint "memory_metadata_user_rating_check";

alter table "dev"."memory_statistics" add constraint "memory_statistics_period_type_check" CHECK (((period_type)::text = ANY ((ARRAY['daily'::character varying, 'weekly'::character varying, 'monthly'::character varying, 'yearly'::character varying])::text[]))) not valid;

alter table "dev"."memory_statistics" validate constraint "memory_statistics_period_type_check";

alter table "dev"."memory_statistics" add constraint "memory_statistics_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."memory_statistics" validate constraint "memory_statistics_user_id_fkey";

alter table "dev"."memory_statistics" add constraint "memory_statistics_user_id_period_type_period_start_key" UNIQUE using index "memory_statistics_user_id_period_type_period_start_key";

alter table "dev"."model_capabilities" add constraint "model_capabilities_model_id_fkey" FOREIGN KEY (model_id) REFERENCES dev.models(model_id) ON DELETE CASCADE not valid;

alter table "dev"."model_capabilities" validate constraint "model_capabilities_model_id_fkey";

alter table "dev"."model_embeddings" add constraint "model_embeddings_model_id_fkey" FOREIGN KEY (model_id) REFERENCES dev.models(model_id) ON DELETE CASCADE not valid;

alter table "dev"."model_embeddings" validate constraint "model_embeddings_model_id_fkey";

alter table "dev"."model_statistics" add constraint "unique_model_daily_stats" UNIQUE using index "unique_model_daily_stats";

alter table "dev"."orders" add constraint "orders_order_id_key" UNIQUE using index "orders_order_id_key";

alter table "dev"."orders" add constraint "orders_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) not valid;

alter table "dev"."orders" validate constraint "orders_user_id_fkey";

alter table "dev"."procedural_memories" add constraint "procedural_memories_difficulty_level_check" CHECK (((difficulty_level >= 1) AND (difficulty_level <= 5))) not valid;

alter table "dev"."procedural_memories" validate constraint "procedural_memories_difficulty_level_check";

alter table "dev"."procedural_memories" add constraint "procedural_memories_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."procedural_memories" validate constraint "procedural_memories_user_id_fkey";

alter table "dev"."procedural_memories" add constraint "procedural_memories_user_id_procedure_name_domain_key" UNIQUE using index "procedural_memories_user_id_procedure_name_domain_key";

alter table "dev"."prompt_embeddings" add constraint "prompt_embeddings_prompt_name_key" UNIQUE using index "prompt_embeddings_prompt_name_key";

alter table "dev"."resource_embeddings" add constraint "resource_embeddings_resource_uri_key" UNIQUE using index "resource_embeddings_resource_uri_key";

alter table "dev"."semantic_memories" add constraint "semantic_memories_mastery_level_check" CHECK (((mastery_level >= (0)::double precision) AND (mastery_level <= (1)::double precision))) not valid;

alter table "dev"."semantic_memories" validate constraint "semantic_memories_mastery_level_check";

alter table "dev"."semantic_memories" add constraint "semantic_memories_parent_concept_id_fkey" FOREIGN KEY (parent_concept_id) REFERENCES dev.semantic_memories(id) not valid;

alter table "dev"."semantic_memories" validate constraint "semantic_memories_parent_concept_id_fkey";

alter table "dev"."semantic_memories" add constraint "semantic_memories_user_id_concept_name_concept_category_key" UNIQUE using index "semantic_memories_user_id_concept_name_concept_category_key";

alter table "dev"."semantic_memories" add constraint "semantic_memories_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."semantic_memories" validate constraint "semantic_memories_user_id_fkey";

alter table "dev"."session_memories" add constraint "session_memories_session_id_key" UNIQUE using index "session_memories_session_id_key";

alter table "dev"."session_memories" add constraint "session_memories_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE not valid;

alter table "dev"."session_memories" validate constraint "session_memories_user_id_fkey";

alter table "dev"."session_messages" add constraint "session_messages_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE not valid;

alter table "dev"."session_messages" validate constraint "session_messages_user_id_fkey";

alter table "dev"."sessions" add constraint "sessions_session_id_key" UNIQUE using index "sessions_session_id_key";

alter table "dev"."sessions" add constraint "sessions_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) not valid;

alter table "dev"."sessions" validate constraint "sessions_user_id_fkey";

alter table "dev"."span_logs" add constraint "span_logs_span_id_fkey" FOREIGN KEY (span_id) REFERENCES dev.spans(span_id) not valid;

alter table "dev"."span_logs" validate constraint "span_logs_span_id_fkey";

alter table "dev"."spans" add constraint "spans_status_check" CHECK ((status = ANY (ARRAY['running'::text, 'completed'::text, 'failed'::text]))) not valid;

alter table "dev"."spans" validate constraint "spans_status_check";

alter table "dev"."spans" add constraint "spans_trace_id_fkey" FOREIGN KEY (trace_id) REFERENCES dev.traces(trace_id) not valid;

alter table "dev"."spans" validate constraint "spans_trace_id_fkey";

alter table "dev"."subscriptions" add constraint "subscriptions_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."subscriptions" validate constraint "subscriptions_user_id_fkey";

alter table "dev"."tool_embeddings" add constraint "tool_embeddings_tool_name_key" UNIQUE using index "tool_embeddings_tool_name_key";

alter table "dev"."traces" add constraint "traces_session_id_fkey" FOREIGN KEY (session_id) REFERENCES dev.sessions(session_id) not valid;

alter table "dev"."traces" validate constraint "traces_session_id_fkey";

alter table "dev"."traces" add constraint "traces_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) not valid;

alter table "dev"."traces" validate constraint "traces_user_id_fkey";

alter table "dev"."user_credit_transactions" add constraint "user_credit_transactions_usage_record_id_fkey" FOREIGN KEY (usage_record_id) REFERENCES dev.user_usage_records(id) ON DELETE SET NULL not valid;

alter table "dev"."user_credit_transactions" validate constraint "user_credit_transactions_usage_record_id_fkey";

alter table "dev"."user_credit_transactions" add constraint "user_credit_transactions_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."user_credit_transactions" validate constraint "user_credit_transactions_user_id_fkey";

alter table "dev"."user_tasks" add constraint "user_tasks_task_id_unique" UNIQUE using index "user_tasks_task_id_unique";

alter table "dev"."user_tasks" add constraint "user_tasks_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) not valid;

alter table "dev"."user_tasks" validate constraint "user_tasks_user_id_fkey";

alter table "dev"."user_usage_records" add constraint "user_usage_records_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."user_usage_records" validate constraint "user_usage_records_user_id_fkey";

alter table "dev"."users" add constraint "users_auth0_id_key" UNIQUE using index "users_auth0_id_key";

alter table "dev"."users" add constraint "users_email_key" UNIQUE using index "users_email_key";

alter table "dev"."users" add constraint "users_user_id_key" UNIQUE using index "users_user_id_key";

alter table "dev"."working_memories" add constraint "working_memories_priority_check" CHECK (((priority >= 1) AND (priority <= 5))) not valid;

alter table "dev"."working_memories" validate constraint "working_memories_priority_check";

alter table "dev"."working_memories" add constraint "working_memories_progress_percentage_check" CHECK (((progress_percentage >= (0)::double precision) AND (progress_percentage <= (100)::double precision))) not valid;

alter table "dev"."working_memories" validate constraint "working_memories_progress_percentage_check";

alter table "dev"."working_memories" add constraint "working_memories_user_id_context_type_context_id_key" UNIQUE using index "working_memories_user_id_context_type_context_id_key";

alter table "dev"."working_memories" add constraint "working_memories_user_id_fkey" FOREIGN KEY (user_id) REFERENCES dev.users(user_id) ON DELETE CASCADE not valid;

alter table "dev"."working_memories" validate constraint "working_memories_user_id_fkey";

set check_function_bodies = off;

CREATE OR REPLACE FUNCTION dev.cleanup_expired_memories()
 RETURNS integer
 LANGUAGE plpgsql
AS $function$
DECLARE
    expired_count INTEGER;
BEGIN
    -- 清理过期的工作记忆
    WITH expired_memories AS (
        UPDATE dev.working_memories 
        SET is_active = false 
        WHERE expires_at < NOW() AND is_active = true
        RETURNING id
    )
    SELECT COUNT(*) INTO expired_count FROM expired_memories;
    
    -- 更新元数据
    UPDATE dev.memory_metadata 
    SET lifecycle_stage = 'archived', updated_at = NOW()
    WHERE memory_type = 'working' 
    AND memory_id IN (
        SELECT id FROM dev.working_memories 
        WHERE expires_at < NOW() AND is_active = false
    );
    
    RETURN expired_count;
END;
$function$
;

CREATE OR REPLACE FUNCTION dev.cleanup_old_metadata_embeddings(days_old integer DEFAULT 30, database_name text DEFAULT NULL::text)
 RETURNS integer
 LANGUAGE plpgsql
AS $function$
DECLARE
    deleted_count integer;
BEGIN
    DELETE FROM dev.db_meta_embedding 
    WHERE created_at < NOW() - INTERVAL '1 day' * days_old
    AND (database_name IS NULL OR database_source = database_name);
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$function$
;

CREATE OR REPLACE FUNCTION dev.find_similar_entities(entity_name_pattern text, entity_type_filter text DEFAULT NULL::text, similarity_threshold double precision DEFAULT 0.7, result_limit integer DEFAULT 5)
 RETURNS TABLE(id text, entity_type text, entity_name text, content text, confidence_score double precision, semantic_tags text[])
 LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        e.id,
        e.entity_type,
        e.entity_name,
        e.content,
        e.confidence_score,
        e.semantic_tags
    FROM dev.db_meta_embedding e
    WHERE 
        (entity_type_filter IS NULL OR e.entity_type = entity_type_filter)
        AND (
            SIMILARITY(e.entity_name, entity_name_pattern) > similarity_threshold
            OR e.entity_name ILIKE '%' || entity_name_pattern || '%'
        )
    ORDER BY SIMILARITY(e.entity_name, entity_name_pattern) DESC
    LIMIT result_limit;
END;
$function$
;

CREATE OR REPLACE FUNCTION dev.get_metadata_stats(database_name text DEFAULT NULL::text)
 RETURNS TABLE(entity_type text, total_entities bigint, avg_confidence double precision, total_semantic_tags bigint)
 LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT 
        e.entity_type,
        COUNT(*) as total_entities,
        AVG(e.confidence_score) as avg_confidence,
        SUM(array_length(e.semantic_tags, 1)) as total_semantic_tags
    FROM dev.db_meta_embedding e
    WHERE (database_name IS NULL OR e.database_source = database_name)
    GROUP BY e.entity_type
    ORDER BY total_entities DESC;
END;
$function$
;

CREATE OR REPLACE FUNCTION dev.match_metadata_embeddings(query_embedding vector, match_threshold double precision DEFAULT 0.0, match_count integer DEFAULT 10, entity_type_filter text DEFAULT NULL::text, database_filter text DEFAULT NULL::text, min_confidence double precision DEFAULT 0.0)
 RETURNS TABLE(id text, entity_type text, entity_name text, entity_full_name text, content text, metadata jsonb, semantic_tags text[], confidence_score double precision, database_source text, created_at timestamp with time zone, similarity double precision)
 LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        e.id,
        e.entity_type,
        e.entity_name,
        e.entity_full_name,
        e.content,
        e.metadata,
        e.semantic_tags,
        e.confidence_score,
        e.database_source,
        e.created_at,
        1 - (e.embedding <=> query_embedding) AS similarity
    FROM dev.db_meta_embedding e
    WHERE 
        (entity_type_filter IS NULL OR e.entity_type = entity_type_filter)
        AND (database_filter IS NULL OR e.database_source = database_filter)
        AND e.confidence_score >= min_confidence
        AND 1 - (e.embedding <=> query_embedding) > match_threshold
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$function$
;

create or replace view "dev"."mcp_search_analytics" as  SELECT date_trunc('day'::text, created_at) AS date,
    count(*) AS total_searches,
    count(DISTINCT user_id) AS unique_users,
    avg(results_count) AS avg_results_count,
    avg(response_time_ms) AS avg_response_time_ms,
    mode() WITHIN GROUP (ORDER BY query) AS most_common_query
   FROM dev.mcp_search_history
  GROUP BY (date_trunc('day'::text, created_at))
  ORDER BY (date_trunc('day'::text, created_at)) DESC;


CREATE OR REPLACE FUNCTION dev.search_memories_by_similarity(p_user_id character varying, p_query_embedding vector, p_memory_types text[] DEFAULT ARRAY['factual'::text, 'procedural'::text, 'episodic'::text, 'semantic'::text], p_limit integer DEFAULT 10, p_threshold double precision DEFAULT 0.7)
 RETURNS TABLE(memory_type text, memory_id uuid, content text, similarity double precision)
 LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    (
        SELECT 'factual'::TEXT, f.id, f.subject || ': ' || f.object_value, 1 - (f.embedding <=> p_query_embedding)
        FROM dev.factual_memories f
        WHERE f.user_id = p_user_id 
        AND f.is_active = true
        AND f.embedding IS NOT NULL
        AND 'factual' = ANY(p_memory_types)
        AND 1 - (f.embedding <=> p_query_embedding) > p_threshold
        
        UNION ALL
        
        SELECT 'procedural'::TEXT, pr.id, pr.procedure_name, 1 - (pr.embedding <=> p_query_embedding)
        FROM dev.procedural_memories pr
        WHERE pr.user_id = p_user_id
        AND pr.embedding IS NOT NULL
        AND 'procedural' = ANY(p_memory_types)
        AND 1 - (pr.embedding <=> p_query_embedding) > p_threshold
        
        UNION ALL
        
        SELECT 'episodic'::TEXT, e.id, e.episode_title, 1 - (e.embedding <=> p_query_embedding)
        FROM dev.episodic_memories e
        WHERE e.user_id = p_user_id
        AND e.embedding IS NOT NULL
        AND 'episodic' = ANY(p_memory_types)
        AND 1 - (e.embedding <=> p_query_embedding) > p_threshold
        
        UNION ALL
        
        SELECT 'semantic'::TEXT, s.id, s.concept_name || ': ' || s.definition, 1 - (s.embedding <=> p_query_embedding)
        FROM dev.semantic_memories s
        WHERE s.user_id = p_user_id
        AND s.embedding IS NOT NULL
        AND 'semantic' = ANY(p_memory_types)
        AND 1 - (s.embedding <=> p_query_embedding) > p_threshold
    )
    ORDER BY similarity DESC
    LIMIT p_limit;
END;
$function$
;

CREATE OR REPLACE FUNCTION dev.track_memory_access(p_user_id character varying, p_memory_type character varying, p_memory_id uuid)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    -- 更新元数据中的访问统计
    INSERT INTO dev.memory_metadata (user_id, memory_type, memory_id, access_count, last_accessed_at)
    VALUES (p_user_id, p_memory_type, p_memory_id, 1, NOW())
    ON CONFLICT (user_id, memory_type, memory_id)
    DO UPDATE SET
        access_count = dev.memory_metadata.access_count + 1,
        last_accessed_at = NOW(),
        updated_at = NOW();
END;
$function$
;

CREATE OR REPLACE FUNCTION dev.update_memory_metadata()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    memory_type_value VARCHAR(20);
BEGIN
    -- 根据表名映射到正确的memory_type
    CASE TG_TABLE_NAME
        WHEN 'factual_memories' THEN memory_type_value := 'factual';
        WHEN 'procedural_memories' THEN memory_type_value := 'procedural';
        WHEN 'episodic_memories' THEN memory_type_value := 'episodic';
        WHEN 'semantic_memories' THEN memory_type_value := 'semantic';
        WHEN 'working_memories' THEN memory_type_value := 'working';
        ELSE memory_type_value := 'unknown';
    END CASE;
    
    -- 更新或插入元数据
    INSERT INTO dev.memory_metadata (user_id, memory_type, memory_id, modification_count, last_modified_at, version)
    VALUES (NEW.user_id, memory_type_value, NEW.id, 1, NOW(), 1)
    ON CONFLICT (user_id, memory_type, memory_id)
    DO UPDATE SET
        modification_count = dev.memory_metadata.modification_count + 1,
        last_modified_at = NOW(),
        version = dev.memory_metadata.version + 1,
        updated_at = NOW();
    
    RETURN NEW;
END;
$function$
;

CREATE OR REPLACE FUNCTION dev.update_metadata_embedding_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$
;

CREATE OR REPLACE FUNCTION dev.update_updated_at_column()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$
;

grant delete on table "dev"."carts" to "anon";

grant insert on table "dev"."carts" to "anon";

grant references on table "dev"."carts" to "anon";

grant select on table "dev"."carts" to "anon";

grant trigger on table "dev"."carts" to "anon";

grant truncate on table "dev"."carts" to "anon";

grant update on table "dev"."carts" to "anon";

grant delete on table "dev"."carts" to "service_role";

grant insert on table "dev"."carts" to "service_role";

grant references on table "dev"."carts" to "service_role";

grant select on table "dev"."carts" to "service_role";

grant trigger on table "dev"."carts" to "service_role";

grant truncate on table "dev"."carts" to "service_role";

grant update on table "dev"."carts" to "service_role";

grant delete on table "dev"."checkpoint_blobs" to "anon";

grant insert on table "dev"."checkpoint_blobs" to "anon";

grant references on table "dev"."checkpoint_blobs" to "anon";

grant select on table "dev"."checkpoint_blobs" to "anon";

grant trigger on table "dev"."checkpoint_blobs" to "anon";

grant truncate on table "dev"."checkpoint_blobs" to "anon";

grant update on table "dev"."checkpoint_blobs" to "anon";

grant delete on table "dev"."checkpoint_blobs" to "service_role";

grant insert on table "dev"."checkpoint_blobs" to "service_role";

grant references on table "dev"."checkpoint_blobs" to "service_role";

grant select on table "dev"."checkpoint_blobs" to "service_role";

grant trigger on table "dev"."checkpoint_blobs" to "service_role";

grant truncate on table "dev"."checkpoint_blobs" to "service_role";

grant update on table "dev"."checkpoint_blobs" to "service_role";

grant delete on table "dev"."checkpoint_migrations" to "anon";

grant insert on table "dev"."checkpoint_migrations" to "anon";

grant references on table "dev"."checkpoint_migrations" to "anon";

grant select on table "dev"."checkpoint_migrations" to "anon";

grant trigger on table "dev"."checkpoint_migrations" to "anon";

grant truncate on table "dev"."checkpoint_migrations" to "anon";

grant update on table "dev"."checkpoint_migrations" to "anon";

grant delete on table "dev"."checkpoint_migrations" to "service_role";

grant insert on table "dev"."checkpoint_migrations" to "service_role";

grant references on table "dev"."checkpoint_migrations" to "service_role";

grant select on table "dev"."checkpoint_migrations" to "service_role";

grant trigger on table "dev"."checkpoint_migrations" to "service_role";

grant truncate on table "dev"."checkpoint_migrations" to "service_role";

grant update on table "dev"."checkpoint_migrations" to "service_role";

grant delete on table "dev"."checkpoint_writes" to "anon";

grant insert on table "dev"."checkpoint_writes" to "anon";

grant references on table "dev"."checkpoint_writes" to "anon";

grant select on table "dev"."checkpoint_writes" to "anon";

grant trigger on table "dev"."checkpoint_writes" to "anon";

grant truncate on table "dev"."checkpoint_writes" to "anon";

grant update on table "dev"."checkpoint_writes" to "anon";

grant delete on table "dev"."checkpoint_writes" to "service_role";

grant insert on table "dev"."checkpoint_writes" to "service_role";

grant references on table "dev"."checkpoint_writes" to "service_role";

grant select on table "dev"."checkpoint_writes" to "service_role";

grant trigger on table "dev"."checkpoint_writes" to "service_role";

grant truncate on table "dev"."checkpoint_writes" to "service_role";

grant update on table "dev"."checkpoint_writes" to "service_role";

grant delete on table "dev"."checkpoints" to "anon";

grant insert on table "dev"."checkpoints" to "anon";

grant references on table "dev"."checkpoints" to "anon";

grant select on table "dev"."checkpoints" to "anon";

grant trigger on table "dev"."checkpoints" to "anon";

grant truncate on table "dev"."checkpoints" to "anon";

grant update on table "dev"."checkpoints" to "anon";

grant delete on table "dev"."checkpoints" to "service_role";

grant insert on table "dev"."checkpoints" to "service_role";

grant references on table "dev"."checkpoints" to "service_role";

grant select on table "dev"."checkpoints" to "service_role";

grant trigger on table "dev"."checkpoints" to "service_role";

grant truncate on table "dev"."checkpoints" to "service_role";

grant update on table "dev"."checkpoints" to "service_role";

grant delete on table "dev"."db_meta_embedding" to "anon";

grant insert on table "dev"."db_meta_embedding" to "anon";

grant references on table "dev"."db_meta_embedding" to "anon";

grant select on table "dev"."db_meta_embedding" to "anon";

grant trigger on table "dev"."db_meta_embedding" to "anon";

grant truncate on table "dev"."db_meta_embedding" to "anon";

grant update on table "dev"."db_meta_embedding" to "anon";

grant delete on table "dev"."db_meta_embedding" to "service_role";

grant insert on table "dev"."db_meta_embedding" to "service_role";

grant references on table "dev"."db_meta_embedding" to "service_role";

grant select on table "dev"."db_meta_embedding" to "service_role";

grant trigger on table "dev"."db_meta_embedding" to "service_role";

grant truncate on table "dev"."db_meta_embedding" to "service_role";

grant update on table "dev"."db_meta_embedding" to "service_role";

grant delete on table "dev"."episodic_memories" to "anon";

grant insert on table "dev"."episodic_memories" to "anon";

grant references on table "dev"."episodic_memories" to "anon";

grant select on table "dev"."episodic_memories" to "anon";

grant trigger on table "dev"."episodic_memories" to "anon";

grant truncate on table "dev"."episodic_memories" to "anon";

grant update on table "dev"."episodic_memories" to "anon";

grant delete on table "dev"."episodic_memories" to "service_role";

grant insert on table "dev"."episodic_memories" to "service_role";

grant references on table "dev"."episodic_memories" to "service_role";

grant select on table "dev"."episodic_memories" to "service_role";

grant trigger on table "dev"."episodic_memories" to "service_role";

grant truncate on table "dev"."episodic_memories" to "service_role";

grant update on table "dev"."episodic_memories" to "service_role";

grant delete on table "dev"."events" to "anon";

grant insert on table "dev"."events" to "anon";

grant references on table "dev"."events" to "anon";

grant select on table "dev"."events" to "anon";

grant trigger on table "dev"."events" to "anon";

grant truncate on table "dev"."events" to "anon";

grant update on table "dev"."events" to "anon";

grant delete on table "dev"."events" to "service_role";

grant insert on table "dev"."events" to "service_role";

grant references on table "dev"."events" to "service_role";

grant select on table "dev"."events" to "service_role";

grant trigger on table "dev"."events" to "service_role";

grant truncate on table "dev"."events" to "service_role";

grant update on table "dev"."events" to "service_role";

grant delete on table "dev"."factual_memories" to "anon";

grant insert on table "dev"."factual_memories" to "anon";

grant references on table "dev"."factual_memories" to "anon";

grant select on table "dev"."factual_memories" to "anon";

grant trigger on table "dev"."factual_memories" to "anon";

grant truncate on table "dev"."factual_memories" to "anon";

grant update on table "dev"."factual_memories" to "anon";

grant delete on table "dev"."factual_memories" to "service_role";

grant insert on table "dev"."factual_memories" to "service_role";

grant references on table "dev"."factual_memories" to "service_role";

grant select on table "dev"."factual_memories" to "service_role";

grant trigger on table "dev"."factual_memories" to "service_role";

grant truncate on table "dev"."factual_memories" to "service_role";

grant update on table "dev"."factual_memories" to "service_role";

grant delete on table "dev"."langgraph_executions" to "anon";

grant insert on table "dev"."langgraph_executions" to "anon";

grant references on table "dev"."langgraph_executions" to "anon";

grant select on table "dev"."langgraph_executions" to "anon";

grant trigger on table "dev"."langgraph_executions" to "anon";

grant truncate on table "dev"."langgraph_executions" to "anon";

grant update on table "dev"."langgraph_executions" to "anon";

grant delete on table "dev"."langgraph_executions" to "service_role";

grant insert on table "dev"."langgraph_executions" to "service_role";

grant references on table "dev"."langgraph_executions" to "service_role";

grant select on table "dev"."langgraph_executions" to "service_role";

grant trigger on table "dev"."langgraph_executions" to "service_role";

grant truncate on table "dev"."langgraph_executions" to "service_role";

grant update on table "dev"."langgraph_executions" to "service_role";

grant delete on table "dev"."mcp_prompts" to "anon";

grant insert on table "dev"."mcp_prompts" to "anon";

grant references on table "dev"."mcp_prompts" to "anon";

grant select on table "dev"."mcp_prompts" to "anon";

grant trigger on table "dev"."mcp_prompts" to "anon";

grant truncate on table "dev"."mcp_prompts" to "anon";

grant update on table "dev"."mcp_prompts" to "anon";

grant delete on table "dev"."mcp_prompts" to "service_role";

grant insert on table "dev"."mcp_prompts" to "service_role";

grant references on table "dev"."mcp_prompts" to "service_role";

grant select on table "dev"."mcp_prompts" to "service_role";

grant trigger on table "dev"."mcp_prompts" to "service_role";

grant truncate on table "dev"."mcp_prompts" to "service_role";

grant update on table "dev"."mcp_prompts" to "service_role";

grant delete on table "dev"."mcp_resources" to "anon";

grant insert on table "dev"."mcp_resources" to "anon";

grant references on table "dev"."mcp_resources" to "anon";

grant select on table "dev"."mcp_resources" to "anon";

grant trigger on table "dev"."mcp_resources" to "anon";

grant truncate on table "dev"."mcp_resources" to "anon";

grant update on table "dev"."mcp_resources" to "anon";

grant delete on table "dev"."mcp_resources" to "service_role";

grant insert on table "dev"."mcp_resources" to "service_role";

grant references on table "dev"."mcp_resources" to "service_role";

grant select on table "dev"."mcp_resources" to "service_role";

grant trigger on table "dev"."mcp_resources" to "service_role";

grant truncate on table "dev"."mcp_resources" to "service_role";

grant update on table "dev"."mcp_resources" to "service_role";

grant delete on table "dev"."mcp_search_history" to "anon";

grant insert on table "dev"."mcp_search_history" to "anon";

grant references on table "dev"."mcp_search_history" to "anon";

grant select on table "dev"."mcp_search_history" to "anon";

grant trigger on table "dev"."mcp_search_history" to "anon";

grant truncate on table "dev"."mcp_search_history" to "anon";

grant update on table "dev"."mcp_search_history" to "anon";

grant delete on table "dev"."mcp_search_history" to "service_role";

grant insert on table "dev"."mcp_search_history" to "service_role";

grant references on table "dev"."mcp_search_history" to "service_role";

grant select on table "dev"."mcp_search_history" to "service_role";

grant trigger on table "dev"."mcp_search_history" to "service_role";

grant truncate on table "dev"."mcp_search_history" to "service_role";

grant update on table "dev"."mcp_search_history" to "service_role";

grant delete on table "dev"."mcp_tools" to "anon";

grant insert on table "dev"."mcp_tools" to "anon";

grant references on table "dev"."mcp_tools" to "anon";

grant select on table "dev"."mcp_tools" to "anon";

grant trigger on table "dev"."mcp_tools" to "anon";

grant truncate on table "dev"."mcp_tools" to "anon";

grant update on table "dev"."mcp_tools" to "anon";

grant delete on table "dev"."mcp_tools" to "service_role";

grant insert on table "dev"."mcp_tools" to "service_role";

grant references on table "dev"."mcp_tools" to "service_role";

grant select on table "dev"."mcp_tools" to "service_role";

grant trigger on table "dev"."mcp_tools" to "service_role";

grant truncate on table "dev"."mcp_tools" to "service_role";

grant update on table "dev"."mcp_tools" to "service_role";

grant delete on table "dev"."mcp_unified_search_embeddings" to "anon";

grant insert on table "dev"."mcp_unified_search_embeddings" to "anon";

grant references on table "dev"."mcp_unified_search_embeddings" to "anon";

grant select on table "dev"."mcp_unified_search_embeddings" to "anon";

grant trigger on table "dev"."mcp_unified_search_embeddings" to "anon";

grant truncate on table "dev"."mcp_unified_search_embeddings" to "anon";

grant update on table "dev"."mcp_unified_search_embeddings" to "anon";

grant delete on table "dev"."mcp_unified_search_embeddings" to "service_role";

grant insert on table "dev"."mcp_unified_search_embeddings" to "service_role";

grant references on table "dev"."mcp_unified_search_embeddings" to "service_role";

grant select on table "dev"."mcp_unified_search_embeddings" to "service_role";

grant trigger on table "dev"."mcp_unified_search_embeddings" to "service_role";

grant truncate on table "dev"."mcp_unified_search_embeddings" to "service_role";

grant update on table "dev"."mcp_unified_search_embeddings" to "service_role";

grant delete on table "dev"."memory_associations" to "anon";

grant insert on table "dev"."memory_associations" to "anon";

grant references on table "dev"."memory_associations" to "anon";

grant select on table "dev"."memory_associations" to "anon";

grant trigger on table "dev"."memory_associations" to "anon";

grant truncate on table "dev"."memory_associations" to "anon";

grant update on table "dev"."memory_associations" to "anon";

grant delete on table "dev"."memory_associations" to "service_role";

grant insert on table "dev"."memory_associations" to "service_role";

grant references on table "dev"."memory_associations" to "service_role";

grant select on table "dev"."memory_associations" to "service_role";

grant trigger on table "dev"."memory_associations" to "service_role";

grant truncate on table "dev"."memory_associations" to "service_role";

grant update on table "dev"."memory_associations" to "service_role";

grant delete on table "dev"."memory_config" to "anon";

grant insert on table "dev"."memory_config" to "anon";

grant references on table "dev"."memory_config" to "anon";

grant select on table "dev"."memory_config" to "anon";

grant trigger on table "dev"."memory_config" to "anon";

grant truncate on table "dev"."memory_config" to "anon";

grant update on table "dev"."memory_config" to "anon";

grant delete on table "dev"."memory_config" to "service_role";

grant insert on table "dev"."memory_config" to "service_role";

grant references on table "dev"."memory_config" to "service_role";

grant select on table "dev"."memory_config" to "service_role";

grant trigger on table "dev"."memory_config" to "service_role";

grant truncate on table "dev"."memory_config" to "service_role";

grant update on table "dev"."memory_config" to "service_role";

grant delete on table "dev"."memory_extraction_logs" to "anon";

grant insert on table "dev"."memory_extraction_logs" to "anon";

grant references on table "dev"."memory_extraction_logs" to "anon";

grant select on table "dev"."memory_extraction_logs" to "anon";

grant trigger on table "dev"."memory_extraction_logs" to "anon";

grant truncate on table "dev"."memory_extraction_logs" to "anon";

grant update on table "dev"."memory_extraction_logs" to "anon";

grant delete on table "dev"."memory_extraction_logs" to "service_role";

grant insert on table "dev"."memory_extraction_logs" to "service_role";

grant references on table "dev"."memory_extraction_logs" to "service_role";

grant select on table "dev"."memory_extraction_logs" to "service_role";

grant trigger on table "dev"."memory_extraction_logs" to "service_role";

grant truncate on table "dev"."memory_extraction_logs" to "service_role";

grant update on table "dev"."memory_extraction_logs" to "service_role";

grant delete on table "dev"."memory_metadata" to "anon";

grant insert on table "dev"."memory_metadata" to "anon";

grant references on table "dev"."memory_metadata" to "anon";

grant select on table "dev"."memory_metadata" to "anon";

grant trigger on table "dev"."memory_metadata" to "anon";

grant truncate on table "dev"."memory_metadata" to "anon";

grant update on table "dev"."memory_metadata" to "anon";

grant delete on table "dev"."memory_metadata" to "service_role";

grant insert on table "dev"."memory_metadata" to "service_role";

grant references on table "dev"."memory_metadata" to "service_role";

grant select on table "dev"."memory_metadata" to "service_role";

grant trigger on table "dev"."memory_metadata" to "service_role";

grant truncate on table "dev"."memory_metadata" to "service_role";

grant update on table "dev"."memory_metadata" to "service_role";

grant delete on table "dev"."memory_statistics" to "anon";

grant insert on table "dev"."memory_statistics" to "anon";

grant references on table "dev"."memory_statistics" to "anon";

grant select on table "dev"."memory_statistics" to "anon";

grant trigger on table "dev"."memory_statistics" to "anon";

grant truncate on table "dev"."memory_statistics" to "anon";

grant update on table "dev"."memory_statistics" to "anon";

grant delete on table "dev"."memory_statistics" to "service_role";

grant insert on table "dev"."memory_statistics" to "service_role";

grant references on table "dev"."memory_statistics" to "service_role";

grant select on table "dev"."memory_statistics" to "service_role";

grant trigger on table "dev"."memory_statistics" to "service_role";

grant truncate on table "dev"."memory_statistics" to "service_role";

grant update on table "dev"."memory_statistics" to "service_role";

grant delete on table "dev"."model_capabilities" to "anon";

grant insert on table "dev"."model_capabilities" to "anon";

grant references on table "dev"."model_capabilities" to "anon";

grant select on table "dev"."model_capabilities" to "anon";

grant trigger on table "dev"."model_capabilities" to "anon";

grant truncate on table "dev"."model_capabilities" to "anon";

grant update on table "dev"."model_capabilities" to "anon";

grant delete on table "dev"."model_capabilities" to "service_role";

grant insert on table "dev"."model_capabilities" to "service_role";

grant references on table "dev"."model_capabilities" to "service_role";

grant select on table "dev"."model_capabilities" to "service_role";

grant trigger on table "dev"."model_capabilities" to "service_role";

grant truncate on table "dev"."model_capabilities" to "service_role";

grant update on table "dev"."model_capabilities" to "service_role";

grant delete on table "dev"."model_embeddings" to "anon";

grant insert on table "dev"."model_embeddings" to "anon";

grant references on table "dev"."model_embeddings" to "anon";

grant select on table "dev"."model_embeddings" to "anon";

grant trigger on table "dev"."model_embeddings" to "anon";

grant truncate on table "dev"."model_embeddings" to "anon";

grant update on table "dev"."model_embeddings" to "anon";

grant delete on table "dev"."model_embeddings" to "service_role";

grant insert on table "dev"."model_embeddings" to "service_role";

grant references on table "dev"."model_embeddings" to "service_role";

grant select on table "dev"."model_embeddings" to "service_role";

grant trigger on table "dev"."model_embeddings" to "service_role";

grant truncate on table "dev"."model_embeddings" to "service_role";

grant update on table "dev"."model_embeddings" to "service_role";

grant delete on table "dev"."model_statistics" to "anon";

grant insert on table "dev"."model_statistics" to "anon";

grant references on table "dev"."model_statistics" to "anon";

grant select on table "dev"."model_statistics" to "anon";

grant trigger on table "dev"."model_statistics" to "anon";

grant truncate on table "dev"."model_statistics" to "anon";

grant update on table "dev"."model_statistics" to "anon";

grant delete on table "dev"."model_statistics" to "service_role";

grant insert on table "dev"."model_statistics" to "service_role";

grant references on table "dev"."model_statistics" to "service_role";

grant select on table "dev"."model_statistics" to "service_role";

grant trigger on table "dev"."model_statistics" to "service_role";

grant truncate on table "dev"."model_statistics" to "service_role";

grant update on table "dev"."model_statistics" to "service_role";

grant delete on table "dev"."models" to "anon";

grant insert on table "dev"."models" to "anon";

grant references on table "dev"."models" to "anon";

grant select on table "dev"."models" to "anon";

grant trigger on table "dev"."models" to "anon";

grant truncate on table "dev"."models" to "anon";

grant update on table "dev"."models" to "anon";

grant delete on table "dev"."models" to "service_role";

grant insert on table "dev"."models" to "service_role";

grant references on table "dev"."models" to "service_role";

grant select on table "dev"."models" to "service_role";

grant trigger on table "dev"."models" to "service_role";

grant truncate on table "dev"."models" to "service_role";

grant update on table "dev"."models" to "service_role";

grant delete on table "dev"."orders" to "anon";

grant insert on table "dev"."orders" to "anon";

grant references on table "dev"."orders" to "anon";

grant select on table "dev"."orders" to "anon";

grant trigger on table "dev"."orders" to "anon";

grant truncate on table "dev"."orders" to "anon";

grant update on table "dev"."orders" to "anon";

grant delete on table "dev"."orders" to "service_role";

grant insert on table "dev"."orders" to "service_role";

grant references on table "dev"."orders" to "service_role";

grant select on table "dev"."orders" to "service_role";

grant trigger on table "dev"."orders" to "service_role";

grant truncate on table "dev"."orders" to "service_role";

grant update on table "dev"."orders" to "service_role";

grant delete on table "dev"."procedural_memories" to "anon";

grant insert on table "dev"."procedural_memories" to "anon";

grant references on table "dev"."procedural_memories" to "anon";

grant select on table "dev"."procedural_memories" to "anon";

grant trigger on table "dev"."procedural_memories" to "anon";

grant truncate on table "dev"."procedural_memories" to "anon";

grant update on table "dev"."procedural_memories" to "anon";

grant delete on table "dev"."procedural_memories" to "service_role";

grant insert on table "dev"."procedural_memories" to "service_role";

grant references on table "dev"."procedural_memories" to "service_role";

grant select on table "dev"."procedural_memories" to "service_role";

grant trigger on table "dev"."procedural_memories" to "service_role";

grant truncate on table "dev"."procedural_memories" to "service_role";

grant update on table "dev"."procedural_memories" to "service_role";

grant delete on table "dev"."prompt_embeddings" to "anon";

grant insert on table "dev"."prompt_embeddings" to "anon";

grant references on table "dev"."prompt_embeddings" to "anon";

grant select on table "dev"."prompt_embeddings" to "anon";

grant trigger on table "dev"."prompt_embeddings" to "anon";

grant truncate on table "dev"."prompt_embeddings" to "anon";

grant update on table "dev"."prompt_embeddings" to "anon";

grant delete on table "dev"."prompt_embeddings" to "service_role";

grant insert on table "dev"."prompt_embeddings" to "service_role";

grant references on table "dev"."prompt_embeddings" to "service_role";

grant select on table "dev"."prompt_embeddings" to "service_role";

grant trigger on table "dev"."prompt_embeddings" to "service_role";

grant truncate on table "dev"."prompt_embeddings" to "service_role";

grant update on table "dev"."prompt_embeddings" to "service_role";

grant delete on table "dev"."resource_embeddings" to "anon";

grant insert on table "dev"."resource_embeddings" to "anon";

grant references on table "dev"."resource_embeddings" to "anon";

grant select on table "dev"."resource_embeddings" to "anon";

grant trigger on table "dev"."resource_embeddings" to "anon";

grant truncate on table "dev"."resource_embeddings" to "anon";

grant update on table "dev"."resource_embeddings" to "anon";

grant delete on table "dev"."resource_embeddings" to "service_role";

grant insert on table "dev"."resource_embeddings" to "service_role";

grant references on table "dev"."resource_embeddings" to "service_role";

grant select on table "dev"."resource_embeddings" to "service_role";

grant trigger on table "dev"."resource_embeddings" to "service_role";

grant truncate on table "dev"."resource_embeddings" to "service_role";

grant update on table "dev"."resource_embeddings" to "service_role";

grant delete on table "dev"."semantic_memories" to "anon";

grant insert on table "dev"."semantic_memories" to "anon";

grant references on table "dev"."semantic_memories" to "anon";

grant select on table "dev"."semantic_memories" to "anon";

grant trigger on table "dev"."semantic_memories" to "anon";

grant truncate on table "dev"."semantic_memories" to "anon";

grant update on table "dev"."semantic_memories" to "anon";

grant delete on table "dev"."semantic_memories" to "service_role";

grant insert on table "dev"."semantic_memories" to "service_role";

grant references on table "dev"."semantic_memories" to "service_role";

grant select on table "dev"."semantic_memories" to "service_role";

grant trigger on table "dev"."semantic_memories" to "service_role";

grant truncate on table "dev"."semantic_memories" to "service_role";

grant update on table "dev"."semantic_memories" to "service_role";

grant delete on table "dev"."session_memories" to "anon";

grant insert on table "dev"."session_memories" to "anon";

grant references on table "dev"."session_memories" to "anon";

grant select on table "dev"."session_memories" to "anon";

grant trigger on table "dev"."session_memories" to "anon";

grant truncate on table "dev"."session_memories" to "anon";

grant update on table "dev"."session_memories" to "anon";

grant delete on table "dev"."session_memories" to "service_role";

grant insert on table "dev"."session_memories" to "service_role";

grant references on table "dev"."session_memories" to "service_role";

grant select on table "dev"."session_memories" to "service_role";

grant trigger on table "dev"."session_memories" to "service_role";

grant truncate on table "dev"."session_memories" to "service_role";

grant update on table "dev"."session_memories" to "service_role";

grant delete on table "dev"."session_messages" to "anon";

grant insert on table "dev"."session_messages" to "anon";

grant references on table "dev"."session_messages" to "anon";

grant select on table "dev"."session_messages" to "anon";

grant trigger on table "dev"."session_messages" to "anon";

grant truncate on table "dev"."session_messages" to "anon";

grant update on table "dev"."session_messages" to "anon";

grant delete on table "dev"."session_messages" to "service_role";

grant insert on table "dev"."session_messages" to "service_role";

grant references on table "dev"."session_messages" to "service_role";

grant select on table "dev"."session_messages" to "service_role";

grant trigger on table "dev"."session_messages" to "service_role";

grant truncate on table "dev"."session_messages" to "service_role";

grant update on table "dev"."session_messages" to "service_role";

grant delete on table "dev"."sessions" to "anon";

grant insert on table "dev"."sessions" to "anon";

grant references on table "dev"."sessions" to "anon";

grant select on table "dev"."sessions" to "anon";

grant trigger on table "dev"."sessions" to "anon";

grant truncate on table "dev"."sessions" to "anon";

grant update on table "dev"."sessions" to "anon";

grant delete on table "dev"."sessions" to "service_role";

grant insert on table "dev"."sessions" to "service_role";

grant references on table "dev"."sessions" to "service_role";

grant select on table "dev"."sessions" to "service_role";

grant trigger on table "dev"."sessions" to "service_role";

grant truncate on table "dev"."sessions" to "service_role";

grant update on table "dev"."sessions" to "service_role";

grant delete on table "dev"."span_logs" to "anon";

grant insert on table "dev"."span_logs" to "anon";

grant references on table "dev"."span_logs" to "anon";

grant select on table "dev"."span_logs" to "anon";

grant trigger on table "dev"."span_logs" to "anon";

grant truncate on table "dev"."span_logs" to "anon";

grant update on table "dev"."span_logs" to "anon";

grant delete on table "dev"."span_logs" to "service_role";

grant insert on table "dev"."span_logs" to "service_role";

grant references on table "dev"."span_logs" to "service_role";

grant select on table "dev"."span_logs" to "service_role";

grant trigger on table "dev"."span_logs" to "service_role";

grant truncate on table "dev"."span_logs" to "service_role";

grant update on table "dev"."span_logs" to "service_role";

grant delete on table "dev"."spans" to "anon";

grant insert on table "dev"."spans" to "anon";

grant references on table "dev"."spans" to "anon";

grant select on table "dev"."spans" to "anon";

grant trigger on table "dev"."spans" to "anon";

grant truncate on table "dev"."spans" to "anon";

grant update on table "dev"."spans" to "anon";

grant delete on table "dev"."spans" to "service_role";

grant insert on table "dev"."spans" to "service_role";

grant references on table "dev"."spans" to "service_role";

grant select on table "dev"."spans" to "service_role";

grant trigger on table "dev"."spans" to "service_role";

grant truncate on table "dev"."spans" to "service_role";

grant update on table "dev"."spans" to "service_role";

grant delete on table "dev"."subscriptions" to "anon";

grant insert on table "dev"."subscriptions" to "anon";

grant references on table "dev"."subscriptions" to "anon";

grant select on table "dev"."subscriptions" to "anon";

grant trigger on table "dev"."subscriptions" to "anon";

grant truncate on table "dev"."subscriptions" to "anon";

grant update on table "dev"."subscriptions" to "anon";

grant delete on table "dev"."subscriptions" to "service_role";

grant insert on table "dev"."subscriptions" to "service_role";

grant references on table "dev"."subscriptions" to "service_role";

grant select on table "dev"."subscriptions" to "service_role";

grant trigger on table "dev"."subscriptions" to "service_role";

grant truncate on table "dev"."subscriptions" to "service_role";

grant update on table "dev"."subscriptions" to "service_role";

grant delete on table "dev"."tool_embeddings" to "anon";

grant insert on table "dev"."tool_embeddings" to "anon";

grant references on table "dev"."tool_embeddings" to "anon";

grant select on table "dev"."tool_embeddings" to "anon";

grant trigger on table "dev"."tool_embeddings" to "anon";

grant truncate on table "dev"."tool_embeddings" to "anon";

grant update on table "dev"."tool_embeddings" to "anon";

grant delete on table "dev"."tool_embeddings" to "service_role";

grant insert on table "dev"."tool_embeddings" to "service_role";

grant references on table "dev"."tool_embeddings" to "service_role";

grant select on table "dev"."tool_embeddings" to "service_role";

grant trigger on table "dev"."tool_embeddings" to "service_role";

grant truncate on table "dev"."tool_embeddings" to "service_role";

grant update on table "dev"."tool_embeddings" to "service_role";

grant delete on table "dev"."traces" to "anon";

grant insert on table "dev"."traces" to "anon";

grant references on table "dev"."traces" to "anon";

grant select on table "dev"."traces" to "anon";

grant trigger on table "dev"."traces" to "anon";

grant truncate on table "dev"."traces" to "anon";

grant update on table "dev"."traces" to "anon";

grant delete on table "dev"."traces" to "service_role";

grant insert on table "dev"."traces" to "service_role";

grant references on table "dev"."traces" to "service_role";

grant select on table "dev"."traces" to "service_role";

grant trigger on table "dev"."traces" to "service_role";

grant truncate on table "dev"."traces" to "service_role";

grant update on table "dev"."traces" to "service_role";

grant delete on table "dev"."user_credit_transactions" to "anon";

grant insert on table "dev"."user_credit_transactions" to "anon";

grant references on table "dev"."user_credit_transactions" to "anon";

grant select on table "dev"."user_credit_transactions" to "anon";

grant trigger on table "dev"."user_credit_transactions" to "anon";

grant truncate on table "dev"."user_credit_transactions" to "anon";

grant update on table "dev"."user_credit_transactions" to "anon";

grant delete on table "dev"."user_credit_transactions" to "service_role";

grant insert on table "dev"."user_credit_transactions" to "service_role";

grant references on table "dev"."user_credit_transactions" to "service_role";

grant select on table "dev"."user_credit_transactions" to "service_role";

grant trigger on table "dev"."user_credit_transactions" to "service_role";

grant truncate on table "dev"."user_credit_transactions" to "service_role";

grant update on table "dev"."user_credit_transactions" to "service_role";

grant delete on table "dev"."user_knowledge" to "anon";

grant insert on table "dev"."user_knowledge" to "anon";

grant references on table "dev"."user_knowledge" to "anon";

grant select on table "dev"."user_knowledge" to "anon";

grant trigger on table "dev"."user_knowledge" to "anon";

grant truncate on table "dev"."user_knowledge" to "anon";

grant update on table "dev"."user_knowledge" to "anon";

grant delete on table "dev"."user_knowledge" to "service_role";

grant insert on table "dev"."user_knowledge" to "service_role";

grant references on table "dev"."user_knowledge" to "service_role";

grant select on table "dev"."user_knowledge" to "service_role";

grant trigger on table "dev"."user_knowledge" to "service_role";

grant truncate on table "dev"."user_knowledge" to "service_role";

grant update on table "dev"."user_knowledge" to "service_role";

grant delete on table "dev"."user_tasks" to "anon";

grant insert on table "dev"."user_tasks" to "anon";

grant references on table "dev"."user_tasks" to "anon";

grant select on table "dev"."user_tasks" to "anon";

grant trigger on table "dev"."user_tasks" to "anon";

grant truncate on table "dev"."user_tasks" to "anon";

grant update on table "dev"."user_tasks" to "anon";

grant delete on table "dev"."user_tasks" to "service_role";

grant insert on table "dev"."user_tasks" to "service_role";

grant references on table "dev"."user_tasks" to "service_role";

grant select on table "dev"."user_tasks" to "service_role";

grant trigger on table "dev"."user_tasks" to "service_role";

grant truncate on table "dev"."user_tasks" to "service_role";

grant update on table "dev"."user_tasks" to "service_role";

grant delete on table "dev"."user_usage_records" to "anon";

grant insert on table "dev"."user_usage_records" to "anon";

grant references on table "dev"."user_usage_records" to "anon";

grant select on table "dev"."user_usage_records" to "anon";

grant trigger on table "dev"."user_usage_records" to "anon";

grant truncate on table "dev"."user_usage_records" to "anon";

grant update on table "dev"."user_usage_records" to "anon";

grant delete on table "dev"."user_usage_records" to "service_role";

grant insert on table "dev"."user_usage_records" to "service_role";

grant references on table "dev"."user_usage_records" to "service_role";

grant select on table "dev"."user_usage_records" to "service_role";

grant trigger on table "dev"."user_usage_records" to "service_role";

grant truncate on table "dev"."user_usage_records" to "service_role";

grant update on table "dev"."user_usage_records" to "service_role";

grant delete on table "dev"."users" to "anon";

grant insert on table "dev"."users" to "anon";

grant references on table "dev"."users" to "anon";

grant select on table "dev"."users" to "anon";

grant trigger on table "dev"."users" to "anon";

grant truncate on table "dev"."users" to "anon";

grant update on table "dev"."users" to "anon";

grant delete on table "dev"."users" to "service_role";

grant insert on table "dev"."users" to "service_role";

grant references on table "dev"."users" to "service_role";

grant select on table "dev"."users" to "service_role";

grant trigger on table "dev"."users" to "service_role";

grant truncate on table "dev"."users" to "service_role";

grant update on table "dev"."users" to "service_role";

grant delete on table "dev"."working_memories" to "anon";

grant insert on table "dev"."working_memories" to "anon";

grant references on table "dev"."working_memories" to "anon";

grant select on table "dev"."working_memories" to "anon";

grant trigger on table "dev"."working_memories" to "anon";

grant truncate on table "dev"."working_memories" to "anon";

grant update on table "dev"."working_memories" to "anon";

grant delete on table "dev"."working_memories" to "service_role";

grant insert on table "dev"."working_memories" to "service_role";

grant references on table "dev"."working_memories" to "service_role";

grant select on table "dev"."working_memories" to "service_role";

grant trigger on table "dev"."working_memories" to "service_role";

grant truncate on table "dev"."working_memories" to "service_role";

grant update on table "dev"."working_memories" to "service_role";

CREATE TRIGGER update_db_meta_embedding_updated_at BEFORE UPDATE ON dev.db_meta_embedding FOR EACH ROW EXECUTE FUNCTION dev.update_metadata_embedding_updated_at();

CREATE TRIGGER episodic_metadata_trigger AFTER INSERT OR UPDATE ON dev.episodic_memories FOR EACH ROW EXECUTE FUNCTION dev.update_memory_metadata();

CREATE TRIGGER factual_metadata_trigger AFTER INSERT OR UPDATE ON dev.factual_memories FOR EACH ROW EXECUTE FUNCTION dev.update_memory_metadata();

CREATE TRIGGER update_mcp_unified_search_embeddings_updated_at BEFORE UPDATE ON dev.mcp_unified_search_embeddings FOR EACH ROW EXECUTE FUNCTION dev.update_updated_at_column();

CREATE TRIGGER procedural_metadata_trigger AFTER INSERT OR UPDATE ON dev.procedural_memories FOR EACH ROW EXECUTE FUNCTION dev.update_memory_metadata();

CREATE TRIGGER semantic_metadata_trigger AFTER INSERT OR UPDATE ON dev.semantic_memories FOR EACH ROW EXECUTE FUNCTION dev.update_memory_metadata();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON dev.users FOR EACH ROW EXECUTE FUNCTION dev.update_updated_at_column();

CREATE TRIGGER working_metadata_trigger AFTER INSERT OR UPDATE ON dev.working_memories FOR EACH ROW EXECUTE FUNCTION dev.update_memory_metadata();


create extension if not exists "vector" with schema "public" version '0.8.0';


create schema if not exists "staging";


create schema if not exists "test";


