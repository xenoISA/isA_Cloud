-- Advanced Security Module for OpenResty
-- Implements WAF rules, attack detection, and IP reputation

local redis = require "resty.redis"
local cjson = require "cjson"

local _M = {}

-- Configuration
local REDIS_HOST = os.getenv("REDIS_HOST") or "redis"
local REDIS_PORT = tonumber(os.getenv("REDIS_PORT")) or 6379
local BLOCK_DURATION = 3600  -- 1 hour

-- SQL Injection patterns
local SQL_PATTERNS = {
    "union.*select",
    "concat%s*%(",
    "declare%s*@",
    "exec%s*%(",
    "execute%s*%(",
    "insert%s+into",
    "select%s+from",
    "delete%s+from",
    "drop%s+table",
    "update%s+.*set"
}

-- XSS patterns
local XSS_PATTERNS = {
    "<script",
    "javascript:",
    "onerror%s*=",
    "onload%s*=",
    "onclick%s*=",
    "onfocus%s*=",
    "onmouseover%s*=",
    "<iframe",
    "document%.cookie",
    "document%.write"
}

-- Path traversal patterns
local PATH_TRAVERSAL_PATTERNS = {
    "%.%./",
    "/etc/passwd",
    "/proc/self",
    "\\.\\.\\",
    "%%2e%%2e",
    "c:\\windows"
}

-- File inclusion patterns
local FILE_INCLUSION_PATTERNS = {
    "php://input",
    "file://",
    "data://",
    "expect://",
    "zip://"
}

-- Connect to Redis
local function connect_redis()
    local red = redis:new()
    red:set_timeout(1000)

    local ok, err = red:connect(REDIS_HOST, REDIS_PORT)
    if not ok then
        return nil, err
    end

    return red
end

-- Check if IP is blocked
local function is_ip_blocked(ip)
    local red, err = connect_redis()
    if not red then
        return false  -- Fail open if Redis is down
    end

    local blocked, err = red:get("blocked:ip:" .. ip)
    red:set_keepalive(10000, 100)

    return blocked ~= ngx.null
end

-- Block an IP address
local function block_ip(ip, reason, duration)
    local red, err = connect_redis()
    if not red then
        ngx.log(ngx.ERR, "Failed to block IP in Redis: ", err)
        return false
    end

    duration = duration or BLOCK_DURATION

    red:setex("blocked:ip:" .. ip, duration, reason)
    red:set_keepalive(10000, 100)

    ngx.log(ngx.WARN, "Blocked IP: ", ip, " Reason: ", reason)
    return true
end

-- Increment attack counter
local function increment_attack_counter(ip)
    local red, err = connect_redis()
    if not red then
        return 0
    end

    local key = "attacks:ip:" .. ip
    local count, err = red:incr(key)

    if count == 1 then
        -- Set expiry on first increment
        red:expire(key, 300)  -- 5 minutes
    end

    red:set_keepalive(10000, 100)
    return count or 0
end

-- Check string against patterns
local function check_patterns(str, patterns)
    if not str then
        return false
    end

    str = string.lower(str)

    for _, pattern in ipairs(patterns) do
        if string.find(str, pattern) then
            return true, pattern
        end
    end

    return false
end

-- Detect SQL injection
local function detect_sql_injection(args, uri)
    local found, pattern = check_patterns(args, SQL_PATTERNS)
    if found then
        return true, "SQL Injection: " .. pattern
    end

    found, pattern = check_patterns(uri, SQL_PATTERNS)
    if found then
        return true, "SQL Injection in URI: " .. pattern
    end

    return false
end

-- Detect XSS
local function detect_xss(args, uri)
    local found, pattern = check_patterns(args, XSS_PATTERNS)
    if found then
        return true, "XSS Attack: " .. pattern
    end

    found, pattern = check_patterns(uri, XSS_PATTERNS)
    if found then
        return true, "XSS in URI: " .. pattern
    end

    return false
end

-- Detect path traversal
local function detect_path_traversal(uri)
    local found, pattern = check_patterns(uri, PATH_TRAVERSAL_PATTERNS)
    if found then
        return true, "Path Traversal: " .. pattern
    end

    return false
end

-- Detect file inclusion
local function detect_file_inclusion(args)
    local found, pattern = check_patterns(args, FILE_INCLUSION_PATTERNS)
    if found then
        return true, "File Inclusion: " .. pattern
    end

    return false
end

-- Main security check
function _M.check()
    local client_ip = ngx.var.remote_addr
    local uri = ngx.var.request_uri
    local args = ngx.var.args or ""
    local user_agent = ngx.var.http_user_agent or ""

    -- Check if IP is already blocked
    if is_ip_blocked(client_ip) then
        ngx.log(ngx.WARN, "Blocked IP attempted access: ", client_ip)
        ngx.status = ngx.HTTP_FORBIDDEN
        ngx.header.content_type = "application/json"
        ngx.say(cjson.encode({
            error = "access_denied",
            message = "Your IP address has been blocked due to suspicious activity"
        }))
        ngx.exit(ngx.HTTP_FORBIDDEN)
    end

    -- Run attack detection
    local attack_detected = false
    local attack_reason = ""

    -- SQL Injection check
    local found, reason = detect_sql_injection(args, uri)
    if found then
        attack_detected = true
        attack_reason = reason
    end

    -- XSS check
    if not attack_detected then
        found, reason = detect_xss(args, uri)
        if found then
            attack_detected = true
            attack_reason = reason
        end
    end

    -- Path Traversal check
    if not attack_detected then
        found, reason = detect_path_traversal(uri)
        if found then
            attack_detected = true
            attack_reason = reason
        end
    end

    -- File Inclusion check
    if not attack_detected then
        found, reason = detect_file_inclusion(args)
        if found then
            attack_detected = true
            attack_reason = reason
        end
    end

    -- If attack detected, increment counter and potentially block
    if attack_detected then
        local attack_count = increment_attack_counter(client_ip)

        ngx.log(ngx.WARN, "Attack detected from ", client_ip, ": ", attack_reason, " (Count: ", attack_count, ")")

        -- Block IP after 5 attacks within 5 minutes
        if attack_count >= 5 then
            block_ip(client_ip, attack_reason, BLOCK_DURATION)
        end

        -- Return 403 Forbidden
        ngx.status = ngx.HTTP_FORBIDDEN
        ngx.header.content_type = "application/json"
        ngx.say(cjson.encode({
            error = "security_violation",
            message = "Request blocked due to security policy",
            incident_id = ngx.var.request_id
        }))
        ngx.exit(ngx.HTTP_FORBIDDEN)
    end
end

-- Verify JWT token (basic validation)
function _M.verify_jwt(token)
    if not token then
        return false, "No token provided"
    end

    -- Remove Bearer prefix if present
    token = string.gsub(token, "^Bearer%s+", "")

    -- Split token into parts
    local parts = {}
    for part in string.gmatch(token, "[^%.]+") do
        table.insert(parts, part)
    end

    if #parts ~= 3 then
        return false, "Invalid token format"
    end

    -- In production, you would:
    -- 1. Decode the header and payload (base64)
    -- 2. Verify the signature using the secret key
    -- 3. Check expiration time
    -- 4. Validate issuer and audience

    return true, nil
end

return _M
