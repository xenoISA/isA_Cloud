-- Redis-backed HTTP response caching
-- Provides intelligent caching with TTL and cache invalidation

local redis = require "resty.redis"
local cjson = require "cjson"

local _M = {}

-- Configuration
local REDIS_HOST = os.getenv("REDIS_HOST") or "redis"
local REDIS_PORT = tonumber(os.getenv("REDIS_PORT")) or 6379
local REDIS_TIMEOUT = 1000
local DEFAULT_TTL = 300  -- 5 minutes

-- Connect to Redis
local function connect_redis()
    local red = redis:new()
    red:set_timeout(REDIS_TIMEOUT)

    local ok, err = red:connect(REDIS_HOST, REDIS_PORT)
    if not ok then
        ngx.log(ngx.ERR, "Failed to connect to Redis: ", err)
        return nil, err
    end

    return red
end

-- Generate cache key from request
local function generate_cache_key()
    local uri = ngx.var.request_uri
    local method = ngx.var.request_method
    local auth = ngx.var.http_authorization or ""

    -- Only cache GET requests
    if method ~= "GET" then
        return nil
    end

    -- Don't cache authenticated requests (unless explicitly allowed)
    if auth ~= "" then
        return nil
    end

    return "cache:http:" .. ngx.md5(uri)
end

-- Check if response should be cached
local function is_cacheable()
    -- Only cache GET requests
    if ngx.var.request_method ~= "GET" then
        return false
    end

    -- Don't cache if Cache-Control: no-cache or no-store
    local cache_control = ngx.var.http_cache_control
    if cache_control then
        if string.find(cache_control, "no-cache") or string.find(cache_control, "no-store") then
            return false
        end
    end

    -- Don't cache authenticated requests by default
    if ngx.var.http_authorization then
        return false
    end

    return true
end

-- Retrieve cached response
function _M.get_cache()
    if not is_cacheable() then
        return
    end

    local cache_key = generate_cache_key()
    if not cache_key then
        return
    end

    local red, err = connect_redis()
    if not red then
        ngx.log(ngx.WARN, "Redis unavailable for cache retrieval")
        return
    end

    -- Get cached response
    local cached, err = red:get(cache_key)
    red:set_keepalive(10000, 100)

    if cached == ngx.null or not cached then
        -- Cache miss
        ngx.header["X-Cache"] = "MISS"
        return
    end

    -- Cache hit
    local response = cjson.decode(cached)

    ngx.status = response.status
    ngx.header["X-Cache"] = "HIT"
    ngx.header["Content-Type"] = response.content_type

    -- Set cache headers
    if response.cached_at then
        local age = ngx.now() - response.cached_at
        ngx.header["Age"] = math.floor(age)
    end

    ngx.say(response.body)
    ngx.exit(ngx.HTTP_OK)
end

-- Store response in cache
function _M.set_cache()
    if not is_cacheable() then
        return
    end

    local cache_key = generate_cache_key()
    if not cache_key then
        return
    end

    -- Only cache successful responses
    if ngx.status ~= ngx.HTTP_OK then
        return
    end

    local red, err = connect_redis()
    if not red then
        ngx.log(ngx.WARN, "Redis unavailable for cache storage")
        return
    end

    -- Get response body
    local response_body = ngx.arg[1]

    -- Build cache entry
    local cache_entry = {
        status = ngx.status,
        content_type = ngx.header["Content-Type"] or "application/json",
        body = response_body,
        cached_at = ngx.now()
    }

    -- Determine TTL from Cache-Control header
    local ttl = DEFAULT_TTL
    local cache_control = ngx.header["Cache-Control"]
    if cache_control then
        local max_age = string.match(cache_control, "max%-age=(%d+)")
        if max_age then
            ttl = tonumber(max_age)
        end
    end

    -- Store in Redis
    red:setex(cache_key, ttl, cjson.encode(cache_entry))
    red:set_keepalive(10000, 100)

    ngx.header["X-Cache"] = "MISS"
end

-- Invalidate cache for a specific pattern
function _M.invalidate(pattern)
    local red, err = connect_redis()
    if not red then
        ngx.log(ngx.ERR, "Redis unavailable for cache invalidation")
        return false, err
    end

    -- Find all keys matching pattern
    local keys, err = red:keys("cache:http:" .. pattern .. "*")
    if not keys or #keys == 0 then
        red:set_keepalive(10000, 100)
        return true
    end

    -- Delete all matching keys
    for _, key in ipairs(keys) do
        red:del(key)
    end

    red:set_keepalive(10000, 100)
    return true
end

return _M
