 验证结果总结

  | 功能         | 状态   | 说明                                     |
  |------------|------|----------------------------------------|
  | 服务注册       | ✅ 成功 | 可以注册服务到 Consul                         |
  | 路由 Meta 传递 | ✅ 成功 | api_path, auth_required, methods 等信息完整 |
  | 服务发现       | ✅ 成功 | discover_service() 返回所有健康实例            |
  | 获取端点       | ✅ 成功 | get_service_endpoint() 返回服务 URL        |
  | 获取路由信息     | ✅ 成功 | 通过 meta 字段获取 API 路径                    |

  ---
  📋 isa_common/consul_client.py 功能确认

  ✅ 服务注册功能

  from isa_common.consul_client import ConsulRegistry

  consul = ConsulRegistry(
      service_name='account_service',
      service_port=8202,
      consul_host='consul-agent-shared',  # 连接 agent
      consul_port=8500,
      tags=['v1', 'user-microservice', 'api'],
      meta={
          'api_path': '/api/v1/accounts',      # ✅ 路由信息
          'auth_required': 'true',             # ✅ 认证要求
          'methods': 'GET,POST,PUT,DELETE'     # ✅ 支持的方法
      },
      health_check_type='http'  # 或 'ttl'
  )

  # 注册到 Consul
  consul.register()

  ✅ 服务发现功能

  # 创建发现客户端
  discovery = ConsulRegistry(consul_host='consul-agent-shared', consul_port=8500)

  # 方式1: 发现所有实例（带路由信息）
  instances = discovery.discover_service('account_service')
  for inst in instances:
      print(f"地址: {inst['address']}:{inst['port']}")
      print(f"路由: {inst['meta']['api_path']}")           # ✅ /api/v1/accounts
      print(f"认证: {inst['meta']['auth_required']}")      # ✅ true
      print(f"方法: {inst['meta']['methods']}")            # ✅ GET,POST,...

  # 方式2: 获取单个端点
  endpoint = discovery.get_service_endpoint('account_service')
  # 返回: http://user-staging:8202

  # 构建完整请求 URL
  instances = discovery.discover_service('account_service')
  base_url = endpoint
  api_path = instances[0]['meta']['api_path']
  full_url = f"{base_url}{api_path}/user123"
  # 结果: http://user-staging:8202/api/v1/accounts/user123

  ---
  🎯 实际使用场景示例

  场景：billing_service 调用 account_service

  # 在 billing_service 中
  from isa_common.consul_client import ConsulRegistry
  import httpx

  # 创建 Consul 客户端
  discovery = ConsulRegistry(consul_host='consul-agent-shared', consul_port=8500)

  # 发现 account_service
  instances = discovery.discover_service('account_service')

  if instances:
      inst = instances[0]

      # 获取服务信息
      base_url = f"http://{inst['address']}:{inst['port']}"
      api_path = inst['meta'].get('api_path', '')
      auth_required = inst['meta'].get('auth_required') == 'true'

      # 构建完整 URL
      full_url = f"{base_url}{api_path}/check-user/user123"

      # 发起请求
      async with httpx.AsyncClient() as client:
          headers = {}
          if auth_required:
              headers['Authorization'] = f'Bearer {token}'

          response = await client.get(full_url, headers=headers)
          print(f"调用成功: {response.json()}")

  ---
  ✅ 总结：完整功能确认

  isa_common/consul_client.py 已经完全支持：

  1. 服务注册

  - ✅ 动态注册（通过 API）
  - ✅ 连接到 agent 或 server
  - ✅ 支持 HTTP 和 TTL 健康检查
  - ✅ 传递 meta 路由信息
  - ✅ 自动清理陈旧注册

  2. 服务发现

  - ✅ 发现健康的服务实例
  - ✅ 获取服务地址和端口
  - ✅ 获取 meta 路由信息（api_path, auth_required, etc.）
  - ✅ 支持负载均衡策略（random, round_robin, health_weighted）
  - ✅ 支持 fallback URL

  3. 路由信息传递

  - ✅ api_path: API 路径（如 /api/v1/accounts）
  - ✅ auth_required: 是否需要认证
  - ✅ methods: 支持的 HTTP 方法
  - ✅ 任意自定义 meta 字段