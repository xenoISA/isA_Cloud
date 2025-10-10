-- MCP Dev Database Sample Data - Simple Version
-- Generated: 2025-07-02

-- Sample Users
INSERT INTO dev.users (username, email, metadata) VALUES
('dev_user', 'dev@mcp.local', '{"role": "developer", "environment": "dev"}'),
('test_user', 'test@mcp.local', '{"role": "tester", "environment": "dev"}'),
('admin_user', 'admin@mcp.local', '{"role": "admin", "environment": "dev"}');

-- Sample Services
INSERT INTO dev.services (name, description, endpoint, config) VALUES
('mcp_server', 'Main MCP Server', 'http://localhost:8081', '{"version": "1.0.0", "environment": "dev"}'),
('user_service', 'User Management Service', 'http://localhost:8100', '{"version": "1.0.0", "environment": "dev"}'),
('event_service', 'Event Sourcing Service', 'http://localhost:8101', '{"version": "1.0.0", "environment": "dev"}');

-- Sample Tool Embeddings (core MCP functionality)
INSERT INTO dev.tool_embeddings (tool_name, description, category, keywords) VALUES
('generate_image', 'Generate images using AI models', 'ai_generation', ARRAY['image', 'ai', 'generation', 'creative']),
('weather', 'Get current weather information', 'external_api', ARRAY['weather', 'api', 'location', 'forecast']),
('recall', 'Retrieve stored memories and information', 'memory', ARRAY['memory', 'recall', 'search', 'retrieval']),
('automate_file_download', 'Automatically download files from URLs', 'automation', ARRAY['download', 'file', 'url', 'automation']),
('web_search', 'Search the web for information', 'external_api', ARRAY['search', 'web', 'internet', 'information']);

-- Sample Tool Selections
INSERT INTO dev.tool_selections (user_request, selected_tools, similarities, confidence_score, user_id) VALUES
('generate a image of a cat', '["generate_image"]', '{"generate_image": 0.95, "weather": 0.1}', 0.95, 1),
('what is the weather like today', '["weather"]', '{"weather": 0.98}', 0.98, 1),
('help me remember something', '["recall"]', '{"recall": 0.92}', 0.92, 2);

-- Sample Traces
INSERT INTO dev.traces (trace_id, operation_name, status, start_time, end_time, duration, user_id, metadata) VALUES
('trace_001', 'mcp_discover', 'completed', NOW() - INTERVAL '1 hour', NOW() - INTERVAL '58 minutes', 120.5, 1, '{"tools_found": 8}'),
('trace_002', 'tool_execution', 'completed', NOW() - INTERVAL '30 minutes', NOW() - INTERVAL '29 minutes', 45.2, 1, '{"tool": "generate_image"}');

-- Sample Spans
INSERT INTO dev.spans (span_id, trace_id, operation_name, status, start_time, end_time, duration, metadata) VALUES
('span_001', 'trace_001', 'tool_search', 'completed', NOW() - INTERVAL '1 hour', NOW() - INTERVAL '59 minutes', 60.2, '{"search_terms": ["image"]}'),
('span_002', 'trace_002', 'tool_call', 'completed', NOW() - INTERVAL '30 minutes', NOW() - INTERVAL '29 minutes', 45.2, '{"tool": "generate_image"}');

-- Sample Span Logs
INSERT INTO dev.span_logs (span_id, level, message, metadata) VALUES
('span_001', 'info', 'Starting tool search for user request', '{"user_id": 1}'),
('span_001', 'debug', 'Found 5 potential tools', '{"tool_count": 5}'),
('span_002', 'info', 'Executing tool: generate_image', '{"tool": "generate_image"}'),
('span_002', 'info', 'Tool execution completed successfully', '{"result": "success"}');