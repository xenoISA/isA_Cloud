-- Advanced Rate Limiting with Lua
-- Implements token bucket algorithm with Redis backend

local redis = require "resty.redis"
local cjson = require "cjson"

local _M = {}

-- Configuration
local REDIS_HOST = os.getenv("REDIS_HOST") or "redis"
local REDIS_PORT = tonumber(os.getenv("REDIS_PORT")) or 6379
local REDIS_TIMEOUT = 1000  -- milliseconds

-- Rate limit tiers (requests per second)
local TIER_LIMITS = {
    free = 10,
    pro = 50,
    enterprise = 200
}

local BURST_MULTIPLIER = 2

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

-- Get user tier from JWT or API key
local function get_user_tier(auth_header)
    if not auth_header then
        return "free"
    end

    -- Extract tier from JWT (simplified - in production, decode JWT properly)
    -- This is a placeholder - you should decode the JWT and extract the tier claim
    local tier = ngx.var.http_x_subscription_tier or "free"

    if TIER_LIMITS[tier] then
        return tier
    end

    return "free"
end

-- Token bucket rate limiting
local function check_rate_limit(key, limit, burst)
    local red, err = connect_redis()
    if not red then
        -- Fail open if Redis is down
        ngx.log(ngx.WARN, "Redis unavailable, allowing request")
        return true
    end

    local now = ngx.now()
    local bucket_key = "ratelimit:" .. key

    -- Get current bucket state
    local bucket, err = red:get(bucket_key)
    if bucket == ngx.null then
        -- Initialize new bucket
        bucket = cjson.encode({
            tokens = burst,
            last_update = now
        })
    end

    local state = cjson.decode(bucket)

    -- Calculate tokens to add based on time elapsed
    local elapsed = now - state.last_update
    local tokens_to_add = elapsed * limit

    state.tokens = math.min(burst, state.tokens + tokens_to_add)
    state.last_update = now

    -- Check if we can allow this request
    if state.tokens >= 1 then
        -- Allow request and consume token
        state.tokens = state.tokens - 1

        -- Save updated state
        red:setex(bucket_key, 60, cjson.encode(state))

        -- Set remaining tokens header
        ngx.header["X-RateLimit-Limit"] = limit
        ngx.header["X-RateLimit-Remaining"] = math.floor(state.tokens)
        ngx.header["X-RateLimit-Reset"] = math.ceil(now + (burst - state.tokens) / limit)

        -- Close Redis connection
        red:set_keepalive(10000, 100)

        return true
    else
        -- Rate limit exceeded
        local retry_after = math.ceil((1 - state.tokens) / limit)

        ngx.header["X-RateLimit-Limit"] = limit
        ngx.header["X-RateLimit-Remaining"] = 0
        ngx.header["X-RateLimit-Reset"] = math.ceil(now + retry_after)
        ngx.header["Retry-After"] = retry_after

        -- Close Redis connection
        red:set_keepalive(10000, 100)

        return false
    end
end

-- Main rate limiting function
function _M.limit()
    -- Get user identifier
    local auth_header = ngx.var.http_authorization
    local user_id = ngx.var.http_x_user_id
    local api_key = ngx.var.http_x_api_key
    local client_ip = ngx.var.remote_addr

    -- Determine rate limit key
    local key
    if user_id then
        key = "user:" .. user_id
    elseif api_key then
        key = "apikey:" .. string.sub(api_key, 1, 10)
    else
        key = "ip:" .. client_ip
    end

    -- Get user tier
    local tier = get_user_tier(auth_header)
    local limit = TIER_LIMITS[tier]
    local burst = limit * BURST_MULTIPLIER

    -- Check rate limit
    local allowed = check_rate_limit(key, limit, burst)

    if not allowed then
        ngx.status = ngx.HTTP_TOO_MANY_REQUESTS
        ngx.header.content_type = "application/json"
        ngx.say(cjson.encode({
            error = "rate_limit_exceeded",
            message = "Too many requests. Please try again later.",
            tier = tier,
            limit = limit .. " req/s"
        }))
        ngx.exit(ngx.HTTP_TOO_MANY_REQUESTS)
    end
end

return _M
