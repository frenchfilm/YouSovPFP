local key = ARGV[1]
local range_as_string = ARGV[2]

-- check if the set is empty and add bag values
if redis.call('SCARD', key) == 0 then
    for i in string.gmatch(range_as_string, "%d+") do
        redis.call('SADD', key, i)
    end
end

local random_value = redis.call('SRANDMEMBER', key)

redis.call('SREM', key, random_value)
return random_value