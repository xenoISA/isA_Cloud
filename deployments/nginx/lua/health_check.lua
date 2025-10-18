-- Active Health Checking for Upstream Servers
-- Monitors backend gateway instances and marks unhealthy ones

local http = require "resty.http"
local cjson = require "cjson"

local _M = {}

-- Configuration
local CHECK_INTERVAL = 5  -- seconds
local TIMEOUT = 2000  -- milliseconds
local UNHEALTHY_THRESHOLD = 3  -- consecutive failures
local HEALTHY_THRESHOLD = 2  -- consecutive successes

-- Upstream servers (read from environment or config)
local UPSTREAM_SERVERS = {
    {host = "gateway", port = 8000, path = "/health"},
    -- Add more gateway instances here
    -- {host = "gateway-2", port = 8000, path = "/health"},
}

-- Health status storage (shared dict)
local health_dict = ngx.shared.cache

-- Check single upstream server
local function check_server(server)
    local httpc = http.new()
    httpc:set_timeout(TIMEOUT)

    local url = string.format("http://%s:%d%s", server.host, server.port, server.path)
    local res, err = httpc:request_uri(url, {
        method = "GET",
        headers = {
            ["User-Agent"] = "OpenResty-HealthCheck/1.0"
        }
    })

    if not res then
        return false, err
    end

    if res.status >= 200 and res.status < 300 then
        return true, nil
    end

    return false, "HTTP " .. res.status
end

-- Update server health status
local function update_health_status(server_key, is_healthy)
    local current_status = health_dict:get(server_key .. ":status") or "unknown"
    local fail_count = health_dict:get(server_key .. ":fail_count") or 0
    local success_count = health_dict:get(server_key .. ":success_count") or 0

    if is_healthy then
        success_count = success_count + 1
        fail_count = 0

        if success_count >= HEALTHY_THRESHOLD then
            if current_status ~= "healthy" then
                ngx.log(ngx.NOTICE, "Server ", server_key, " is now healthy")
            end
            health_dict:set(server_key .. ":status", "healthy")
        end
    else
        fail_count = fail_count + 1
        success_count = 0

        if fail_count >= UNHEALTHY_THRESHOLD then
            if current_status ~= "unhealthy" then
                ngx.log(ngx.ERR, "Server ", server_key, " is now unhealthy")
            end
            health_dict:set(server_key .. ":status", "unhealthy")
        end
    end

    health_dict:set(server_key .. ":fail_count", fail_count)
    health_dict:set(server_key .. ":success_count", success_count)
    health_dict:set(server_key .. ":last_check", ngx.now())
end

-- Health check worker
function _M.check_all()
    for _, server in ipairs(UPSTREAM_SERVERS) do
        local server_key = server.host .. ":" .. server.port

        local ok, err = check_server(server)

        if ok then
            update_health_status(server_key, true)
        else
            ngx.log(ngx.WARN, "Health check failed for ", server_key, ": ", err or "unknown error")
            update_health_status(server_key, false)
        end
    end
end

-- Get health status of a server
function _M.get_status(host, port)
    local server_key = host .. ":" .. port
    local status = health_dict:get(server_key .. ":status")
    return status or "unknown"
end

-- Get all server health statuses
function _M.get_all_statuses()
    local statuses = {}

    for _, server in ipairs(UPSTREAM_SERVERS) do
        local server_key = server.host .. ":" .. server.port
        local status = health_dict:get(server_key .. ":status") or "unknown"
        local last_check = health_dict:get(server_key .. ":last_check") or 0

        table.insert(statuses, {
            host = server.host,
            port = server.port,
            status = status,
            last_check = last_check
        })
    end

    return statuses
end

-- Initialize health checking (called in init_worker_by_lua)
function _M.init_worker()
    local delay = CHECK_INTERVAL

    local function check()
        _M.check_all()
    end

    local ok, err = ngx.timer.every(delay, check)
    if not ok then
        ngx.log(ngx.ERR, "Failed to create health check timer: ", err)
        return
    end

    ngx.log(ngx.NOTICE, "Health check worker started (interval: ", delay, "s)")
end

-- HTTP handler to expose health status
function _M.status_handler()
    ngx.header.content_type = "application/json"

    local statuses = _M.get_all_statuses()

    local all_healthy = true
    for _, status in ipairs(statuses) do
        if status.status ~= "healthy" then
            all_healthy = false
            break
        end
    end

    local response = {
        healthy = all_healthy,
        upstreams = statuses,
        timestamp = ngx.now()
    }

    ngx.say(cjson.encode(response))
end

return _M
